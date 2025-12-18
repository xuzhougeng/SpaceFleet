/**
 * API 模块 - 封装所有后端 API 调用
 */

// 使用相对路径，自动适配任意端口
const API_BASE = '/api';

const api = {
    /**
     * 通用请求方法
     */
    async request(endpoint, options = {}) {
        const url = `${API_BASE}${endpoint}`;
        const config = {
            headers: {
                'Content-Type': 'application/json',
            },
            ...options,
        };

        try {
            const response = await fetch(url, config);
            
            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.detail || `HTTP ${response.status}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error(`API Error [${endpoint}]:`, error);
            throw error;
        }
    },

    // ===== 服务器相关 =====
    
    /**
     * 获取所有服务器
     */
    async getServers() {
        return this.request('/servers/');
    },

    /**
     * 获取单个服务器
     */
    async getServer(id) {
        return this.request(`/servers/${id}`);
    },

    /**
     * 创建服务器
     */
    async createServer(data) {
        return this.request('/servers/', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    /**
     * 更新服务器
     */
    async updateServer(id, data) {
        return this.request(`/servers/${id}`, {
            method: 'PUT',
            body: JSON.stringify(data),
        });
    },

    /**
     * 删除服务器
     */
    async deleteServer(id) {
        return this.request(`/servers/${id}`, {
            method: 'DELETE',
        });
    },

    /**
     * 测试服务器连接
     */
    async testConnection(id) {
        return this.request(`/servers/${id}/test`, {
            method: 'POST',
        });
    },

    /**
     * 测试 sudo 是否可用（需要 NOPASSWD）
     */
    async testSudo(id) {
        return this.request(`/servers/${id}/test-sudo`, {
            method: 'POST',
        });
    },

    // ===== 磁盘相关 =====

    /**
     * 获取磁盘概览
     */
    async getDiskSummary() {
        return this.request('/disks/summary');
    },

    /**
     * 获取告警磁盘
     */
    async getDiskAlerts() {
        return this.request('/disks/alerts');
    },

    /**
     * 获取服务器磁盘历史
     */
    async getServerDisks(serverId, limit = 100) {
        return this.request(`/disks/server/${serverId}?limit=${limit}`);
    },

    /**
     * 获取磁盘趋势数据
     */
    async getDiskTrend(serverId, mountPoint, days = 30) {
        // 移除开头的斜杠，因为 API 路径会自动添加
        const mount = mountPoint.startsWith('/') ? mountPoint.slice(1) : mountPoint;
        return this.request(`/disks/trend/${serverId}/${mount}?days=${days}`);
    },

    /**
     * 获取用户空间占用
     */
    async getUserUsage(serverId, mountPoint) {
        const mount = mountPoint.startsWith('/') ? mountPoint.slice(1) : mountPoint;
        return this.request(`/disks/users/${serverId}/${mount}`);
    },

    /**
     * 获取文件类型统计
     */
    async getFileTypes(serverId, mountPoint, force = false) {
        const mount = mountPoint.startsWith('/') ? mountPoint.slice(1) : mountPoint;
        const qs = force ? '?force=true' : '';
        return this.request(`/disks/filetypes/${serverId}/${mount}${qs}`);
    },

    /**
     * 获取最大文件列表
     */
    async getLargeFiles(serverId, mountPoint, limit = 50, force = false) {
        const mount = mountPoint.startsWith('/') ? mountPoint.slice(1) : mountPoint;
        const qs = new URLSearchParams();
        qs.set('limit', limit);
        if (force) qs.set('force', 'true');
        return this.request(`/disks/largefiles/${serverId}/${mount}?${qs.toString()}`);
    },

    /**
     * 触发数据采集
     */
    async collectData(serverId = null) {
        const endpoint = serverId 
            ? `/disks/collect?server_id=${serverId}`
            : '/disks/collect';
        return this.request(endpoint, {
            method: 'POST',
        });
    },

    // ===== 健康检查 =====

    /**
     * 检查 API 健康状态
     */
    async healthCheck() {
        return this.request('/health');
    },

    // ===== 服务器指标相关 =====

    /**
     * 获取所有服务器的CPU和内存指标概览
     */
    async getMetricsSummary() {
        return this.request('/disks/metrics/summary');
    },

    /**
     * 获取指定服务器的指标历史数据
     */
    async getServerMetrics(serverId, limit = 100) {
        return this.request(`/disks/metrics/server/${serverId}?limit=${limit}`);
    },

    // ===== 告警配置相关 =====

    /**
     * 获取所有告警配置
     */
    async getAlerts() {
        return this.request('/alerts/');
    },

    /**
     * 获取单个告警配置
     */
    async getAlert(id) {
        return this.request(`/alerts/${id}`);
    },

    /**
     * 创建告警配置
     */
    async createAlert(data) {
        return this.request('/alerts/', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    /**
     * 更新告警配置
     */
    async updateAlert(id, data) {
        return this.request(`/alerts/${id}`, {
            method: 'PUT',
            body: JSON.stringify(data),
        });
    },

    /**
     * 删除告警配置
     */
    async deleteAlert(id) {
        return this.request(`/alerts/${id}`, {
            method: 'DELETE',
        });
    },

    /**
     * 测试告警通知
     */
    async testAlert(id) {
        return this.request(`/alerts/${id}/test`, {
            method: 'POST',
        });
    },
};
