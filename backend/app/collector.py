import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.ssh_client import SSHClient
from app.models import Server, DiskUsage, UserDiskUsage
from app.config import settings


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


def collect_disk_usage(ssh: SSHClient, scan_mounts: Optional[List[str]] = None) -> tuple[List[Dict[str, Any]], List[str]]:
    """
    采集磁盘使用情况
    
    执行 df -hT，过滤 >= 250GB 的分区
    
    Args:
        ssh: SSH 客户端
        scan_mounts: 要扫描的挂载点列表，None 或空列表表示扫描所有
    
    Returns:
        (disks, all_mount_points): 采集到的磁盘列表和服务器上所有可用挂载点
    """
    stdout, stderr, code = ssh.execute("df -hT")
    
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


def collect_user_usage(ssh: SSHClient, mount_point: str) -> List[Dict[str, Any]]:
    """
    采集指定挂载点下各一级目录的空间占用
    """
    # 使用 du 统计一级子目录
    cmd = f"du -s {mount_point}/*  2>/dev/null | sort -rn"
    stdout, stderr, code = ssh.execute(cmd)
    
    # du 可能部分失败（权限问题），但仍返回部分结果
    if not stdout.strip():
        return []
    
    # 获取目录所有者
    owner_cmd = f"stat -c '%U %n' {mount_point}/*  2>/dev/null"
    owner_stdout, _, _ = ssh.execute(owner_cmd)
    
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
            
            # 解析配置的扫描挂载点
            scan_mounts = None
            if server.scan_mounts:
                scan_mounts = [m.strip() for m in server.scan_mounts.split(',') if m.strip()]
            
            # 采集磁盘使用情况
            disks, all_mount_points = collect_disk_usage(ssh, scan_mounts)
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
                    users = collect_user_usage(ssh, disk['mount_point'])
                    
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
    servers = db.query(Server).all()
    results = []
    
    for server in servers:
        result = collect_server_data(db, server)
        results.append(result)
    
    return results
