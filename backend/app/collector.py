import re
from datetime import datetime
from typing import List, Dict, Any, Optional
import shlex
from sqlalchemy.orm import Session

from app.ssh_client import SSHClient
from app.models import Server, DiskUsage, UserDiskUsage, ServerMetrics
from app.config import settings


def _wrap_sudo(command: str, use_sudo: bool) -> str:
    if not use_sudo:
        return command
    # -n: non-interactive, fail fast if password is required
    return f"sudo -n bash -lc {shlex.quote(command)}"


def parse_size_to_gb(size_str: str) -> float:
    """
    将大小字符串转换为 GB
    支持: 100G, 1.5T, 500M, 1024K
    """
    size_str = size_str.strip().upper()
    
    match = re.match(r'^([\d.]+)([KMGTP]?)B?$', size_str)
    if not match:
        return 0.0
    
    value = float(match.group(1))
    unit = match.group(2)
    
    multipliers = {
        'K': 1 / (1024 * 1024),
        'M': 1 / 1024,
        'G': 1,
        'T': 1024,
        'P': 1024 * 1024,
        '': 1 / (1024 * 1024 * 1024),  # bytes
    }
    
    return value * multipliers.get(unit, 1)


def collect_disk_usage(
    ssh: SSHClient,
    scan_mounts: Optional[List[str]] = None,
    use_sudo: bool = False,
) -> tuple[List[Dict[str, Any]], List[str]]:
    """
    采集磁盘使用情况
    
    执行 df -hT，过滤 >= 250GB 的分区
    
    Args:
        ssh: SSH 客户端
        scan_mounts: 要扫描的挂载点列表，None 或空列表表示扫描所有
    
    Returns:
        (disks, all_mount_points): 采集到的磁盘列表和服务器上所有可用挂载点
    """
    stdout, stderr, code = ssh.execute(_wrap_sudo("df -hT", use_sudo))
    
    if code != 0:
        raise RuntimeError(f"Failed to execute df: {stderr}")
    
    disks = []
    all_mount_points = []  # 记录所有可用挂载点，用于提示
    lines = stdout.strip().split('\n')
    
    # 跳过标题行
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 7:
            continue
        
        device = parts[0]
        filesystem = parts[1]
        total_str = parts[2]
        used_str = parts[3]
        free_str = parts[4]
        use_percent_str = parts[5].rstrip('%')
        mount_point = parts[6]
        
        # 跳过 tmpfs, devtmpfs 等虚拟文件系统
        if filesystem in ('tmpfs', 'devtmpfs', 'efivarfs', 'squashfs'):
            continue
        
        # 跳过 boot, efi 分区
        if mount_point in ('/boot', '/boot/efi') or mount_point.startswith('/snap'):
            continue
        
        total_gb = parse_size_to_gb(total_str)
        
        # 记录所有有效挂载点（用于提示用户）
        all_mount_points.append(mount_point)
        
        # 如果配置了指定挂载点，只采集配置中的（忽略大小限制）
        if scan_mounts:
            if mount_point not in scan_mounts:
                continue
        else:
            # 未指定挂载点时，只采集 >= MIN_DISK_SIZE_GB 的分区
            if total_gb < settings.MIN_DISK_SIZE_GB:
                continue
        
        try:
            use_percent = float(use_percent_str)
        except ValueError:
            use_percent = 0.0
        
        disks.append({
            'device': device,
            'filesystem': filesystem,
            'mount_point': mount_point,
            'total_gb': round(total_gb, 2),
            'used_gb': round(parse_size_to_gb(used_str), 2),
            'free_gb': round(parse_size_to_gb(free_str), 2),
            'use_percent': use_percent,
        })
    
    return disks, all_mount_points


def collect_user_usage(ssh: SSHClient, mount_point: str, use_sudo: bool = False) -> List[Dict[str, Any]]:
    """
    采集指定挂载点下各一级目录的空间占用
    """
    # 使用 du 统计一级子目录
    cmd = f"du -s {mount_point}/*  2>/dev/null | sort -rn"
    stdout, stderr, code = ssh.execute(_wrap_sudo(cmd, use_sudo), timeout=3600)
    
    # du 可能部分失败（权限问题），但仍返回部分结果
    if not stdout.strip():
        return []
    
    # 获取目录所有者
    owner_cmd = f"stat -c '%U %n' {mount_point}/*  2>/dev/null"
    owner_stdout, _, _ = ssh.execute(_wrap_sudo(owner_cmd, use_sudo), timeout=3600)
    
    # 解析所有者信息
    owners = {}
    for line in owner_stdout.strip().split('\n'):
        if ' ' in line:
            parts = line.split(' ', 1)
            if len(parts) == 2:
                owners[parts[1]] = parts[0]
    
    users = []
    for line in stdout.strip().split('\n'):
        parts = line.split('\t')
        if len(parts) < 2:
            continue
        
        try:
            size_kb = int(parts[0])
        except ValueError:
            continue
        
        directory = parts[1]
        size_gb = size_kb / (1024 * 1024)  # KB to GB
        
        # 只记录 >= 1GB 的目录
        if size_gb < 1:
            continue
        
        users.append({
            'directory': directory,
            'owner': owners.get(directory, None),
            'used_gb': round(size_gb, 2),
        })
    
    return users


def collect_gpu_info(ssh: SSHClient, use_sudo: bool = False) -> List[Dict[str, Any]]:
    """
    采集GPU使用情况（使用nvidia-smi）
    
    Returns:
        GPU信息列表，每个元素包含:
        {
            'index': int,
            'name': str,
            'memory_total_mb': float,
            'memory_used_mb': float,
            'memory_percent': float,
            'gpu_util_percent': float,
            'temperature': float,
        }
        如果没有GPU或nvidia-smi不可用，返回空列表
    """
    # 使用nvidia-smi查询GPU信息
    # --query-gpu: index,name,memory.total,memory.used,utilization.gpu,temperature.gpu
    # --format=csv,noheader,nounits
    base_cmd = "--query-gpu=index,name,memory.total,memory.used,utilization.gpu,temperature.gpu --format=csv,noheader,nounits"
    gpu_cmds = [
        f"bash -lc \"nvidia-smi {base_cmd} 2>/dev/null\"",
        f"/usr/bin/nvidia-smi {base_cmd} 2>/dev/null",
        f"/usr/local/nvidia/bin/nvidia-smi {base_cmd} 2>/dev/null",
        f"nvidia-smi {base_cmd} 2>/dev/null",
    ]

    gpu_stdout = ""
    for cmd in gpu_cmds:
        out, _, code = ssh.execute(_wrap_sudo(cmd, use_sudo))
        if code == 0 and out.strip():
            gpu_stdout = out
            break

    if not gpu_stdout.strip():
        return []
    
    gpus = []
    for line in gpu_stdout.strip().split('\n'):
        parts = [p.strip() for p in line.split(',')]
        if len(parts) < 6:
            continue
        
        try:
            index = int(parts[0])
            name = parts[1]
            memory_total_mb = float(parts[2])
            memory_used_mb = float(parts[3])
            gpu_util_percent = float(parts[4])
            temperature = float(parts[5])
            
            memory_percent = (memory_used_mb / memory_total_mb * 100) if memory_total_mb > 0 else 0.0
            
            gpus.append({
                'index': index,
                'name': name,
                'memory_total_mb': round(memory_total_mb, 0),
                'memory_used_mb': round(memory_used_mb, 0),
                'memory_percent': round(memory_percent, 2),
                'gpu_util_percent': round(gpu_util_percent, 2),
                'temperature': round(temperature, 1),
            })
        except (ValueError, IndexError):
            continue
    
    return gpus


def collect_server_metrics(ssh: SSHClient, use_sudo: bool = False) -> Dict[str, Any]:
    """
    采集服务器CPU、内存和GPU使用情况
    
    Returns:
        {
            'cpu_percent': float,
            'memory_total_gb': float,
            'memory_used_gb': float,
            'memory_free_gb': float,
            'memory_percent': float,
            'gpu_info': list,  # GPU信息列表
        }
    """
    # CPU使用率：基于 /proc/stat 两次采样（与 top 输出格式/语言无关，更稳定）
    # 公式：cpu% = (delta_total - delta_idle) / delta_total * 100
    cpu_cmd = (
        "sh -lc '"
        "read cpu u n s i w irq si st rest < /proc/stat; "
        "t1=$((u+n+s+i+w+irq+si+st)); idle1=$((i+w)); "
        "sleep 1; "
        "read cpu u n s i w irq si st rest < /proc/stat; "
        "t2=$((u+n+s+i+w+irq+si+st)); idle2=$((i+w)); "
        "dt=$((t2-t1)); didle=$((idle2-idle1)); "
        "if [ \"$dt\" -gt 0 ]; then "
        "awk -v dt=\"$dt\" -v didle=\"$didle\" \"BEGIN{printf \\\"%.2f\\\\n\\\", (dt-didle)*100/dt}\"; "
        "else echo 0.00; fi"
        "'"
    )
    cpu_stdout, _, cpu_code = ssh.execute(_wrap_sudo(cpu_cmd, use_sudo))

    if cpu_code == 0 and (cpu_stdout or "").strip():
        try:
            cpu_percent = float(cpu_stdout.strip())
            if cpu_percent < 0 or cpu_percent > 100:
                cpu_percent = 0.0
        except (ValueError, AttributeError):
            cpu_percent = 0.0
    else:
        # 备用方法：vmstat（部分系统可能未安装）
        cpu_cmd2 = "vmstat 1 2 | tail -1 | awk '{print 100-$15}'"
        cpu_stdout2, _, cpu_code2 = ssh.execute(_wrap_sudo(cpu_cmd2, use_sudo))
        if cpu_code2 == 0 and (cpu_stdout2 or "").strip():
            try:
                cpu_percent = float(cpu_stdout2.strip())
                if cpu_percent < 0 or cpu_percent > 100:
                    cpu_percent = 0.0
            except (ValueError, AttributeError):
                cpu_percent = 0.0
        else:
            cpu_percent = 0.0
    
    # 内存信息：使用 free -b（字节，精度更高；-g 会做整数 GiB 取整）
    mem_cmd = "free -b"
    mem_stdout, _, mem_code = ssh.execute(_wrap_sudo(mem_cmd, use_sudo))
    
    if mem_code != 0:
        raise RuntimeError(f"Failed to collect memory info: exit code {mem_code}")
    
    # 解析free输出
    # Mem:    total   used   free   shared  buff/cache   available
    mem_lines = mem_stdout.strip().split('\n')
    if len(mem_lines) < 2:
        raise RuntimeError("Failed to parse memory info")
    
    mem_parts = mem_lines[1].split()
    if len(mem_parts) < 3:
        raise RuntimeError("Failed to parse memory info")
    
    try:
        total_b = float(mem_parts[1])
        used_b = float(mem_parts[2])
        free_b = float(mem_parts[3]) if len(mem_parts) > 3 else max(total_b - used_b, 0)

        gb = 1024 * 1024 * 1024
        memory_total_gb = total_b / gb
        memory_used_gb = used_b / gb
        memory_free_gb = free_b / gb
        memory_percent = (memory_used_gb / memory_total_gb * 100) if memory_total_gb > 0 else 0.0
    except (ValueError, IndexError) as e:
        raise RuntimeError(f"Failed to parse memory values: {e}")
    
    # 采集GPU信息（可选，失败不影响其他指标）
    try:
        gpu_info = collect_gpu_info(ssh, use_sudo)
    except Exception:
        gpu_info = []
    
    return {
        'cpu_percent': round(cpu_percent, 2),
        'memory_total_gb': round(memory_total_gb, 2),
        'memory_used_gb': round(memory_used_gb, 2),
        'memory_free_gb': round(memory_free_gb, 2),
        'memory_percent': round(memory_percent, 2),
        'gpu_info': gpu_info,
    }


def collect_server_data(db: Session, server: Server) -> Dict[str, Any]:
    """
    采集单个服务器的磁盘数据并存入数据库
    """
    result = {
        'server_id': server.id,
        'server_name': server.name,
        'success': False,
        'error': None,
        'warning': None,
        'disks_collected': 0,
        'users_collected': 0,
        'available_mounts': [],  # 服务器上可用的挂载点
    }
    
    try:
        ssh = SSHClient(
            host=server.host,
            port=server.port,
            username=server.username,
            password=server.password,
            private_key_path=server.private_key_path,
        )
        
        with ssh:
            collected_at = datetime.utcnow()
            use_sudo = bool(getattr(server, 'sudoer', False))
            
            # 解析配置的扫描挂载点
            scan_mounts = None
            if server.scan_mounts:
                scan_mounts = [m.strip() for m in server.scan_mounts.split(',') if m.strip()]
            
            # 采集CPU和内存使用情况
            try:
                metrics = collect_server_metrics(ssh, use_sudo=use_sudo)
                import json as _json
                server_metric = ServerMetrics(
                    server_id=server.id,
                    cpu_percent=metrics['cpu_percent'],
                    memory_total_gb=metrics['memory_total_gb'],
                    memory_used_gb=metrics['memory_used_gb'],
                    memory_free_gb=metrics['memory_free_gb'],
                    memory_percent=metrics['memory_percent'],
                    gpu_info=_json.dumps(metrics.get('gpu_info', []), ensure_ascii=False) if metrics.get('gpu_info') else None,
                    collected_at=collected_at,
                )
                db.add(server_metric)
            except Exception as e:
                # 指标采集失败不影响磁盘采集
                print(f"Warning: Failed to collect metrics for {server.name}: {e}")
            
            # 采集磁盘使用情况
            disks, all_mount_points = collect_disk_usage(ssh, scan_mounts, use_sudo=use_sudo)
            result['available_mounts'] = all_mount_points
            
            # 如果配置了扫描挂载点但没有采集到任何磁盘，给出提示
            if scan_mounts and len(disks) == 0:
                configured = ', '.join(scan_mounts)
                available = ', '.join(all_mount_points) if all_mount_points else '无'
                result['warning'] = f"配置的挂载点 [{configured}] 未找到。服务器可用挂载点: {available}"
            
            for disk in disks:
                disk_usage = DiskUsage(
                    server_id=server.id,
                    device=disk['device'],
                    filesystem=disk['filesystem'],
                    mount_point=disk['mount_point'],
                    total_gb=disk['total_gb'],
                    used_gb=disk['used_gb'],
                    free_gb=disk['free_gb'],
                    use_percent=disk['use_percent'],
                    collected_at=collected_at,
                )
                db.add(disk_usage)
                result['disks_collected'] += 1
                
                # 采集用户空间占用（仅对数据盘）
                # 排除根分区，只分析 /data, /home 等目录
                if disk['mount_point'] not in ('/',):
                    users = collect_user_usage(ssh, disk['mount_point'], use_sudo=use_sudo)
                    
                    for user in users:
                        user_usage = UserDiskUsage(
                            server_id=server.id,
                            mount_point=disk['mount_point'],
                            directory=user['directory'],
                            owner=user['owner'],
                            used_gb=user['used_gb'],
                            collected_at=collected_at,
                        )
                        db.add(user_usage)
                        result['users_collected'] += 1
            
            db.commit()
            result['success'] = True
            
    except Exception as e:
        db.rollback()
        result['error'] = str(e)
    
    return result


def collect_all_servers(db: Session) -> List[Dict[str, Any]]:
    """
    采集所有服务器的磁盘数据
    """
    servers = db.query(Server).filter(Server.enabled == True).all()
    results = []
    
    for server in servers:
        result = collect_server_data(db, server)
        results.append(result)
    
    return results


def collect_all_servers_metrics(db: Session) -> List[Dict[str, Any]]:
    """
    采集所有服务器的CPU和内存指标（不采集磁盘）
    """
    servers = db.query(Server).filter(Server.enabled == True).all()
    results = []
    
    for server in servers:
        result = {
            'server_id': server.id,
            'server_name': server.name,
            'success': False,
            'error': None,
        }
        
        try:
            ssh = SSHClient(
                host=server.host,
                port=server.port,
                username=server.username,
                password=server.password,
                private_key_path=server.private_key_path,
            )
            
            with ssh:
                collected_at = datetime.utcnow()
                use_sudo = bool(getattr(server, 'sudoer', False))
                
                metrics = collect_server_metrics(ssh, use_sudo=use_sudo)
                import json as _json
                server_metric = ServerMetrics(
                    server_id=server.id,
                    cpu_percent=metrics['cpu_percent'],
                    memory_total_gb=metrics['memory_total_gb'],
                    memory_used_gb=metrics['memory_used_gb'],
                    memory_free_gb=metrics['memory_free_gb'],
                    memory_percent=metrics['memory_percent'],
                    gpu_info=_json.dumps(metrics.get('gpu_info', []), ensure_ascii=False) if metrics.get('gpu_info') else None,
                    collected_at=collected_at,
                )
                db.add(server_metric)
                db.commit()
                result['success'] = True
                
        except Exception as e:
            db.rollback()
            result['error'] = str(e)
        
        results.append(result)
    
    return results


def get_file_type_stats(ssh: SSHClient, mount_point: str, use_sudo: bool = False) -> List[Dict[str, Any]]:
    """
    获取指定挂载点下文件类型占比统计
    
    Returns:
        按大小降序排列的文件类型统计列表
    """
    cmd = f"""find {mount_point} -xdev -type f -printf '%s %f\\n' 2>/dev/null | \\
awk '{{
    size = $1
    fname = $2
    # 提取扩展名
    n = split(fname, parts, ".")
    if (n > 1 && length(parts[n]) <= 10) {{
        ext = tolower(parts[n])
    }} else {{
        ext = "no_ext"
    }}
    sizes[ext] += size
    counts[ext]++
}}
END {{
    total = 0
    for (ext in sizes) {{
        total += sizes[ext]
    }}
    for (ext in sizes) {{
        printf "%s\\t%d\\t%d\\t%d\\n", ext, sizes[ext], counts[ext], total
    }}
}}' | sort -t$'\\t' -k2 -rn | head -20"""
    
    stdout, stderr, code = ssh.execute(_wrap_sudo(cmd, use_sudo), timeout=3600)
    
    if not stdout.strip():
        return []
    
    results = []
    total_size = None
    lines = stdout.strip().split('\n')
    
    # 解析各类型
    for line in lines:
        parts = line.split('\t')
        if len(parts) < 4:
            continue
        
        try:
            ext = parts[0]
            size_bytes = int(parts[1])
            count = int(parts[2])
            if total_size is None:
                total_size = int(parts[3])
            size_gb = size_bytes / (1024 * 1024 * 1024)
            percent = (size_bytes / total_size * 100) if total_size and total_size > 0 else 0
            
            results.append({
                'extension': ext,
                'size_gb': round(size_gb, 2),
                'file_count': count,
                'percent': round(percent, 2),
            })
        except ValueError:
            continue
    
    return results


def get_top_large_files(ssh: SSHClient, mount_point: str, limit: int = 50, use_sudo: bool = False) -> List[Dict[str, Any]]:
    """
    获取指定挂载点下最大的文件
    
    Args:
        ssh: SSH 客户端
        mount_point: 挂载点
        limit: 返回数量限制
    
    Returns:
        按大小降序排列的文件列表
    """
    cmd = f"""find {mount_point} -xdev -type f -printf '%s\\t%u\\t%T+\\t%p\\n' 2>/dev/null | \\
awk -v N={limit} 'BEGIN{{for(i=1;i<=N;i++){{s[i]=-1;line[i]=""}}}} {{
    size=$1
    for(i=1;i<=N;i++){{
        if(size>s[i]){{
            for(j=N;j>i;j--){{s[j]=s[j-1];line[j]=line[j-1]}}
            s[i]=size
            line[i]=$0
            break
        }}
    }}
}} END{{for(i=1;i<=N;i++){{if(s[i]>=0) print line[i]}}}}'"""
    
    stdout, stderr, code = ssh.execute(_wrap_sudo(cmd, use_sudo), timeout=3600)
    
    if not stdout.strip():
        return []
    
    results = []
    for line in stdout.strip().split('\n'):
        parts = line.split('\t')
        if len(parts) < 4:
            continue
        
        try:
            size_bytes = int(parts[0])
            owner = parts[1]
            modified = parts[2][:19] if len(parts[2]) >= 19 else parts[2]  # 截取日期时间
            filepath = parts[3]
            
            # 提取扩展名
            filename = filepath.split('/')[-1]
            ext_parts = filename.rsplit('.', 1)
            extension = ext_parts[1].lower() if len(ext_parts) > 1 and len(ext_parts[1]) <= 10 else ''
            
            size_gb = size_bytes / (1024 * 1024 * 1024)
            
            results.append({
                'filepath': filepath,
                'filename': filename,
                'extension': extension,
                'size_gb': round(size_gb, 2),
                'owner': owner,
                'modified': modified,
            })
        except (ValueError, IndexError):
            continue
    
    return results
