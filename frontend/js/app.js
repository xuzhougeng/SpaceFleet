/**
 * 主应用模块
 */

// ===== 全局状态 =====
let servers = [];
let diskSummary = [];
let currentMountPoints = [];

// 采集任务锁定状态
const collectingState = {
    all: false,           // 全局采集中
    servers: new Set(),   // 正在采集的服务器ID集合
};

// ===== 初始化 =====
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initChart();
    loadDashboard();
});

// ===== 导航 =====
function initNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            const page = item.dataset.page;
            switchPage(page);
        });
    });
}

function renderAnalysisMeta(meta, tabName) {
    const collectedAt = meta.collected_at ? new Date(meta.collected_at).toLocaleString() : '无';
    const staleText = meta.is_stale ? '（已过期）' : '';
    const refreshingText = meta.refreshing ? '正在后台刷新...' : '';
    const err = meta.error ? `错误: ${meta.error}` : '';
    return `
        <div class="analysis-meta">
            <div class="analysis-meta-left">
                <span>数据时间: ${collectedAt}${staleText}</span>
                ${refreshingText ? `<span class="analysis-meta-refreshing">${refreshingText}</span>` : ''}
                ${err ? `<span class="analysis-meta-error">${err}</span>` : ''}
            </div>
            <div class="analysis-meta-actions">
                <button class="btn btn-sm btn-secondary" onclick="forceRefreshDetailTab('${tabName}')">🔄 强制刷新</button>
            </div>
        </div>
    `;
}

async function forceRefreshDetailTab(tabName) {
    if (!currentDetailServerId || !currentDetailMountPoint) return;
    const content = document.getElementById('detail-content');
    content.innerHTML = '<div class="loading">强制刷新中...（可能较慢）</div>';
    if (tabName === 'filetypes') {
        await loadFileTypesTab(true);
    } else if (tabName === 'largefiles') {
        await loadLargeFilesTab(true);
    } else {
        await loadDirectoriesTab();
    }
}

function switchPage(pageName) {
    // 更新导航状态
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.page === pageName);
    });
    
    // 切换页面
    document.querySelectorAll('.page').forEach(page => {
        page.classList.toggle('active', page.id === `page-${pageName}`);
    });
    
    // 加载页面数据
    switch (pageName) {
        case 'dashboard':
            loadDashboard();
            break;
        case 'servers':
            loadServers();
            break;
        case 'trends':
            loadTrendPage();
            break;
    }
}

// ===== 仪表盘 =====
async function loadDashboard() {
    const cardsContainer = document.getElementById('disk-cards');
    const alertsSection = document.getElementById('alerts-section');
    const alertsList = document.getElementById('alerts-list');
    
    cardsContainer.innerHTML = '<div class="loading">加载中...</div>';
    
    try {
        diskSummary = await api.getDiskSummary();
        
        if (diskSummary.length === 0) {
            cardsContainer.innerHTML = `
                <div class="empty-state">
                    <div class="icon">📭</div>
                    <p>暂无磁盘数据</p>
                    <p>请先添加服务器并采集数据</p>
                </div>
            `;
            alertsSection.classList.add('hidden');
            return;
        }
        
        // 显示告警
        const alerts = diskSummary.filter(d => d.is_alert);
        if (alerts.length > 0) {
            alertsSection.classList.remove('hidden');
            alertsList.innerHTML = alerts.map(d => 
                `<span class="alert-tag">${d.server_name} ${d.mount_point} (${d.use_percent.toFixed(1)}%)</span>`
            ).join('');
        } else {
            alertsSection.classList.add('hidden');
        }
        
        // 渲染磁盘卡片
        cardsContainer.innerHTML = diskSummary.map(disk => renderDiskCard(disk)).join('');
        
    } catch (error) {
        cardsContainer.innerHTML = `
            <div class="empty-state">
                <div class="icon">❌</div>
                <p>加载失败: ${error.message}</p>
                <p>请确保后端服务已启动</p>
            </div>
        `;
        alertsSection.classList.add('hidden');
    }
}

function renderDiskCard(disk) {
    const percentClass = disk.use_percent >= 90 ? 'danger' : disk.use_percent >= 70 ? 'warning' : '';
    const progressClass = disk.use_percent >= 90 ? 'danger' : disk.use_percent >= 70 ? 'warning' : 'normal';
    const alertClass = disk.is_alert ? 'alert' : '';
    
    return `
        <div class="disk-card ${alertClass}">
            <div class="disk-card-header">
                <div>
                    <div class="disk-card-title">${disk.server_name}</div>
                    <div class="disk-card-mount">${disk.mount_point}</div>
                </div>
                <div class="disk-card-percent ${percentClass}">${disk.use_percent.toFixed(1)}%</div>
            </div>
            <div class="progress-bar">
                <div class="progress-fill ${progressClass}" style="width: ${disk.use_percent}%"></div>
            </div>
            <div class="disk-card-info">
                <span>已用: ${disk.used_gb.toFixed(1)} GB</span>
                <span>可用: ${disk.free_gb.toFixed(1)} GB</span>
                <span>总计: ${disk.total_gb.toFixed(1)} GB</span>
            </div>
            <div class="disk-card-actions">
                <button class="btn btn-sm btn-secondary" onclick="showUserUsage(${disk.server_id}, '${disk.mount_point}')">
                    📁 目录详情
                </button>
                <button class="btn btn-sm btn-secondary" onclick="viewTrend(${disk.server_id}, '${disk.mount_point}')">
                    📈 查看趋势
                </button>
            </div>
        </div>
    `;
}

async function collectAllData() {
    // 防止重复点击
    if (collectingState.all) {
        showToast('正在采集中，请稍候...', 'info');
        return;
    }
    
    collectingState.all = true;
    updateCollectAllButton(true);
    showToast('开始采集数据...', 'info');
    
    try {
        const result = await api.collectData();
        const successCount = result.results.filter(r => r.success).length;
        const failCount = result.results.length - successCount;
        
        // 检查是否有警告信息
        const warnings = result.results.filter(r => r.warning);
        if (warnings.length > 0) {
            warnings.forEach(w => {
                showToast(`⚠️ ${w.server_name}: ${w.warning}`, 'warning');
            });
        }
        
        if (failCount > 0) {
            showToast(`采集完成: ${successCount} 成功, ${failCount} 失败`, 'warning');
        } else if (successCount > 0) {
            const diskCount = result.results.reduce((sum, r) => sum + (r.disks_collected || 0), 0);
            showToast(`采集完成: ${successCount} 台服务器, ${diskCount} 个磁盘`, 'success');
        } else {
            showToast('采集完成，但未采集到任何磁盘', 'warning');
        }
        
        // 刷新仪表盘
        loadDashboard();
    } catch (error) {
        showToast('采集失败: ' + error.message, 'error');
    } finally {
        collectingState.all = false;
        updateCollectAllButton(false);
    }
}

function updateCollectAllButton(isCollecting) {
    const btn = document.querySelector('#page-dashboard .page-header .btn-primary');
    if (btn) {
        btn.disabled = isCollecting;
        btn.innerHTML = isCollecting 
            ? '⏳ 采集中...' 
            : '🔄 采集所有数据';
    }
}

// ===== 服务器管理 =====
async function loadServers() {
    const container = document.getElementById('servers-list');
    container.innerHTML = '<div class="loading">加载中...</div>';
    
    try {
        servers = await api.getServers();
        
        if (servers.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="icon">🖥️</div>
                    <p>暂无服务器</p>
                    <p>点击上方按钮添加服务器</p>
                </div>
            `;
            return;
        }
        
        container.innerHTML = servers.map(server => renderServerCard(server)).join('');
        
    } catch (error) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="icon">❌</div>
                <p>加载失败: ${error.message}</p>
            </div>
        `;
    }
}

function renderServerCard(server) {
    const scanInfo = server.scan_mounts 
        ? `<span class="server-scan">📁 ${server.scan_mounts}</span>` 
        : '<span class="server-scan">📁 所有磁盘</span>';

    const enabled = server.enabled !== false;
    const statusTag = enabled
        ? '<span class="server-status enabled">✅ 启用</span>'
        : '<span class="server-status disabled">🚫 禁用</span>';

    const collectBtn = enabled
        ? `<button class="btn btn-sm btn-secondary" onclick="collectServerData(${server.id})">🔄 采集数据</button>`
        : `<button class="btn btn-sm btn-secondary" disabled>🚫 已禁用</button>`;

    const toggleBtn = enabled
        ? `<button class="btn btn-sm btn-warning" onclick="toggleServerEnabled(${server.id}, false)">🚫 禁用</button>`
        : `<button class="btn btn-sm btn-secondary" onclick="toggleServerEnabled(${server.id}, true)">✅ 启用</button>`;

    return `
        <div class="server-card ${enabled ? '' : 'disabled'}">
            <div class="server-info">
                <div class="server-name">${server.name}</div>
                <div class="server-host">${server.username}@${server.host}:${server.port} ${scanInfo} ${statusTag}</div>
                ${server.description ? `<div class="server-description">${server.description}</div>` : ''}
            </div>
            <div class="server-actions">
                <button class="btn btn-sm btn-secondary" onclick="testConnection(${server.id})">
                    🔌 测试连接
                </button>
                ${collectBtn}
                <button class="btn btn-sm btn-secondary" onclick="editServer(${server.id})">
                    ✏️ 编辑
                </button>
                ${toggleBtn}
                <button class="btn btn-sm btn-danger" onclick="deleteServer(${server.id})">
                    🗑️ 删除
                </button>
            </div>
        </div>
    `;
}

async function toggleServerEnabled(id, enabled) {
    try {
        await api.updateServer(id, { enabled });
        showToast(enabled ? '服务器已启用' : '服务器已禁用', 'success');
        loadServers();
        // 仪表盘数据可能变化
        loadDashboard();
    } catch (error) {
        showToast('操作失败: ' + error.message, 'error');
    }
}

function showAddServerModal() {
    document.getElementById('modal-title').textContent = '添加服务器';
    document.getElementById('server-form').reset();
    document.getElementById('server-id').value = '';
    document.getElementById('server-port').value = '22';
    document.getElementById('server-modal').classList.remove('hidden');
}

async function editServer(id) {
    try {
        const server = await api.getServer(id);
        
        document.getElementById('modal-title').textContent = '编辑服务器';
        document.getElementById('server-id').value = server.id;
        document.getElementById('server-name').value = server.name;
        document.getElementById('server-host').value = server.host;
        document.getElementById('server-port').value = server.port;
        document.getElementById('server-username').value = server.username;
        document.getElementById('server-password').value = '';
        document.getElementById('server-keypath').value = server.private_key_path || '';
        document.getElementById('server-description').value = server.description || '';
        document.getElementById('server-scanmounts').value = server.scan_mounts || '';
        
        document.getElementById('server-modal').classList.remove('hidden');
    } catch (error) {
        showToast('获取服务器信息失败: ' + error.message, 'error');
    }
}

async function saveServer(event) {
    event.preventDefault();
    
    const id = document.getElementById('server-id').value;
    const data = {
        name: document.getElementById('server-name').value,
        host: document.getElementById('server-host').value,
        port: parseInt(document.getElementById('server-port').value) || 22,
        username: document.getElementById('server-username').value,
        description: document.getElementById('server-description').value || null,
        scan_mounts: document.getElementById('server-scanmounts').value || null,
    };
    
    const password = document.getElementById('server-password').value;
    const keyPath = document.getElementById('server-keypath').value;
    
    if (password) data.password = password;
    if (keyPath) data.private_key_path = keyPath;
    
    try {
        if (id) {
            await api.updateServer(id, data);
            showToast('服务器已更新', 'success');
        } else {
            await api.createServer(data);
            showToast('服务器已添加', 'success');
        }
        
        closeModal();
        loadServers();
    } catch (error) {
        showToast('保存失败: ' + error.message, 'error');
    }
}

async function deleteServer(id) {
    if (!confirm('确定要删除这台服务器吗？相关的磁盘数据也会被删除。')) {
        return;
    }
    
    try {
        await api.deleteServer(id);
        showToast('服务器已删除', 'success');
        loadServers();
    } catch (error) {
        showToast('删除失败: ' + error.message, 'error');
    }
}

async function testConnection(id) {
    showToast('正在测试连接...', 'info');
    
    try {
        const result = await api.testConnection(id);
        if (result.success) {
            showToast('连接成功!', 'success');
        } else {
            showToast('连接失败: ' + result.message, 'error');
        }
    } catch (error) {
        showToast('测试失败: ' + error.message, 'error');
    }
}

async function collectServerData(id) {
    const server = servers.find(s => s.id === id);
    if (server && server.enabled === false) {
        showToast('该服务器已禁用，无法采集', 'info');
        return;
    }
    // 防止重复点击
    if (collectingState.servers.has(id) || collectingState.all) {
        showToast('该服务器正在采集中，请稍候...', 'info');
        return;
    }
    
    collectingState.servers.add(id);
    updateServerCollectButton(id, true);
    showToast('正在采集数据...', 'info');
    
    try {
        const result = await api.collectData(id);
        const r = result.results[0];
        
        // 显示警告信息
        if (r.warning) {
            showToast(`⚠️ ${r.warning}`, 'warning');
        }
        
        if (r.success) {
            if (r.disks_collected > 0) {
                showToast(`采集成功: ${r.server_name}, ${r.disks_collected} 个磁盘`, 'success');
            } else {
                showToast(`采集成功但未找到磁盘。可用挂载点: ${r.available_mounts?.join(', ') || '无'}`, 'warning');
            }
        } else {
            showToast(`采集失败: ${r.error}`, 'error');
        }
    } catch (error) {
        showToast('采集失败: ' + error.message, 'error');
    } finally {
        collectingState.servers.delete(id);
        updateServerCollectButton(id, false);
    }
}

function updateServerCollectButton(serverId, isCollecting) {
    const btn = document.querySelector(`button[onclick="collectServerData(${serverId})"]`);
    if (btn) {
        btn.disabled = isCollecting;
        btn.innerHTML = isCollecting 
            ? '⏳ 采集中' 
            : '🔄 采集数据';
    }
}

function closeModal() {
    document.getElementById('server-modal').classList.add('hidden');
}

// ===== 用户空间详情 =====
// 存储当前查看的服务器和挂载点
let currentDetailServerId = null;
let currentDetailMountPoint = null;
let currentDetailTab = 'directories';
let detailPollTimer = null;

async function showUserUsage(serverId, mountPoint) {
    const modal = document.getElementById('users-modal');
    const title = document.getElementById('users-modal-title');
    const list = document.getElementById('users-list');
    
    currentDetailServerId = serverId;
    currentDetailMountPoint = mountPoint;
    
    title.textContent = `目录空间详情 - ${mountPoint}`;
    
    // 创建 Tab 结构
    list.innerHTML = `
        <div class="detail-tabs">
            <button class="tab-btn active" onclick="switchDetailTab(event, 'directories')">📁 目录占用</button>
            <button class="tab-btn" onclick="switchDetailTab(event, 'filetypes')">📊 文件类型</button>
            <button class="tab-btn" onclick="switchDetailTab(event, 'largefiles')">📦 大文件 Top50</button>
        </div>
        <div id="detail-content" class="detail-content">
            <div class="loading">加载中...</div>
        </div>
    `;
    modal.classList.remove('hidden');
    
    // 默认加载目录占用
    await loadDirectoriesTab();
}

async function switchDetailTab(e, tabName) {
    if (detailPollTimer) {
        clearTimeout(detailPollTimer);
        detailPollTimer = null;
    }
    currentDetailTab = tabName;

    // 更新 Tab 按钮状态
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    if (e && e.target) e.target.classList.add('active');
    
    const content = document.getElementById('detail-content');
    content.innerHTML = '<div class="loading">加载中...</div>';
    
    switch (tabName) {
        case 'directories':
            await loadDirectoriesTab();
            break;
        case 'filetypes':
            await loadFileTypesTab();
            break;
        case 'largefiles':
            await loadLargeFilesTab();
            break;
    }
}

async function loadDirectoriesTab() {
    const content = document.getElementById('detail-content');
    
    try {
        const data = await api.getUserUsage(currentDetailServerId, currentDetailMountPoint);
        
        if (data.length === 0) {
            content.innerHTML = '<div class="empty-state"><p>暂无目录数据</p></div>';
            return;
        }
        
        content.innerHTML = `
            <table class="users-table">
                <thead>
                    <tr>
                        <th>目录</th>
                        <th>所有者</th>
                        <th>占用空间</th>
                        <th>占比</th>
                    </tr>
                </thead>
                <tbody>
                    ${data.map(item => `
                        <tr>
                            <td>${item.directory}</td>
                            <td>${item.owner || '-'}</td>
                            <td>${item.used_gb.toFixed(2)} GB</td>
                            <td>${item.percent_of_disk.toFixed(1)}%</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    } catch (error) {
        content.innerHTML = `<div class="empty-state"><p>加载失败: ${error.message}</p></div>`;
    }
}

async function loadFileTypesTab(force = false) {
    const content = document.getElementById('detail-content');
    
    try {
        const resp = await api.getFileTypes(currentDetailServerId, currentDetailMountPoint, force);
        const data = resp.items || [];
        
        const metaHtml = renderAnalysisMeta(resp, 'filetypes');

        if (resp.refreshing && !force) {
            detailPollTimer = setTimeout(() => {
                if (currentDetailTab === 'filetypes' && currentDetailServerId && currentDetailMountPoint) {
                    loadFileTypesTab(false);
                }
            }, 5000);
        }

        if (data.length === 0) {
            content.innerHTML = metaHtml + '<div class="empty-state"><p>暂无文件类型数据（可能正在后台扫描）</p></div>';
            return;
        }
        
        content.innerHTML = `
            ${metaHtml}
            <table class="users-table">
                <thead>
                    <tr>
                        <th>文件类型</th>
                        <th>占用空间</th>
                        <th>文件数量</th>
                        <th>占比</th>
                    </tr>
                </thead>
                <tbody>
                    ${data.map(item => `
                        <tr>
                            <td><span class="file-ext">${item.extension === 'no_ext' ? '无扩展名' : '.' + item.extension}</span></td>
                            <td>${item.size_gb.toFixed(2)} GB</td>
                            <td>${item.file_count.toLocaleString()}</td>
                            <td>
                                <div class="percent-bar-container">
                                    <div class="percent-bar" style="width: ${Math.min(item.percent, 100)}%"></div>
                                    <span>${item.percent.toFixed(1)}%</span>
                                </div>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    } catch (error) {
        content.innerHTML = `<div class="empty-state"><p>加载失败: ${error.message}</p></div>`;
    }
}

async function loadLargeFilesTab(force = false) {
    const content = document.getElementById('detail-content');
    
    try {
        const resp = await api.getLargeFiles(currentDetailServerId, currentDetailMountPoint, 50, force);
        const data = resp.items || [];

        const metaHtml = renderAnalysisMeta(resp, 'largefiles');

        if (resp.refreshing && !force) {
            detailPollTimer = setTimeout(() => {
                if (currentDetailTab === 'largefiles' && currentDetailServerId && currentDetailMountPoint) {
                    loadLargeFilesTab(false);
                }
            }, 5000);
        }
        
        if (data.length === 0) {
            content.innerHTML = metaHtml + '<div class="empty-state"><p>暂无大文件数据（可能正在后台扫描）</p></div>';
            return;
        }
        
        content.innerHTML = `
            ${metaHtml}
            <table class="users-table large-files-table">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>文件名</th>
                        <th>大小</th>
                        <th>所有者</th>
                        <th>修改时间</th>
                    </tr>
                </thead>
                <tbody>
                    ${data.map((item, index) => `
                        <tr>
                            <td class="rank-cell">${index + 1}</td>
                            <td>
                                <div class="file-info">
                                    <span class="filename" title="${item.filepath}">${item.filename}</span>
                                    <span class="filepath">${item.filepath}</span>
                                </div>
                            </td>
                            <td class="size-cell">${item.size_gb.toFixed(2)} GB</td>
                            <td>${item.owner}</td>
                            <td class="date-cell">${item.modified.replace('T', ' ')}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    } catch (error) {
        content.innerHTML = `<div class="empty-state"><p>加载失败: ${error.message}</p></div>`;
    }
}

function closeUsersModal() {
    document.getElementById('users-modal').classList.add('hidden');
    if (detailPollTimer) {
        clearTimeout(detailPollTimer);
        detailPollTimer = null;
    }
    currentDetailServerId = null;
    currentDetailMountPoint = null;
    currentDetailTab = 'directories';
}

// ===== 趋势分析 =====
async function loadTrendPage() {
    const serverSelect = document.getElementById('trend-server');
    
    try {
        servers = await api.getServers();
        
        serverSelect.innerHTML = '<option value="">选择服务器</option>' +
            servers.map(s => `<option value="${s.id}">${s.name}</option>`).join('');
        
        // 清空图表
        updateChart([], { title: '磁盘使用趋势' });
        
    } catch (error) {
        showToast('加载服务器列表失败', 'error');
    }
}

async function loadMountPoints() {
    const serverId = document.getElementById('trend-server').value;
    const mountSelect = document.getElementById('trend-mount');
    
    if (!serverId) {
        mountSelect.innerHTML = '<option value="">选择挂载点</option>';
        return;
    }
    
    try {
        // 从磁盘概览中获取该服务器的挂载点
        const summary = await api.getDiskSummary();
        currentMountPoints = summary.filter(d => d.server_id == serverId);
        
        mountSelect.innerHTML = '<option value="">选择挂载点</option>' +
            currentMountPoints.map(d => `<option value="${d.mount_point}">${d.mount_point}</option>`).join('');
            
    } catch (error) {
        showToast('加载挂载点失败', 'error');
    }
}

async function loadTrendData() {
    const serverId = document.getElementById('trend-server').value;
    const mountPoint = document.getElementById('trend-mount').value;
    const days = document.getElementById('trend-days').value;
    
    if (!serverId || !mountPoint) {
        return;
    }
    
    try {
        const data = await api.getDiskTrend(serverId, mountPoint, days);
        
        if (data.length === 0) {
            updateChart([], { title: '暂无趋势数据' });
            return;
        }
        
        const chartData = data.map(d => ({
            date: d.date,
            value: d.use_percent,
        }));
        
        const serverName = servers.find(s => s.id == serverId)?.name || '';
        
        updateChart(chartData, {
            title: `${serverName} - ${mountPoint} 使用率趋势`,
            yMin: 0,
            yMax: 100,
        });
        
    } catch (error) {
        showToast('加载趋势数据失败: ' + error.message, 'error');
    }
}

function viewTrend(serverId, mountPoint) {
    // 切换到趋势页面
    switchPage('trends');
    
    // 设置选择器
    setTimeout(async () => {
        document.getElementById('trend-server').value = serverId;
        await loadMountPoints();
        document.getElementById('trend-mount').value = mountPoint;
        loadTrendData();
    }, 100);
}

// ===== Toast 通知 =====
function showToast(message, type = 'info') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type}`;
    
    // 3秒后隐藏
    setTimeout(() => {
        toast.classList.add('hidden');
    }, 3000);
}

// ===== 点击模态框外部关闭 =====
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal')) {
        e.target.classList.add('hidden');
    }
});
