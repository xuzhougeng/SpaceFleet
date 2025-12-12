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
    async getFileTypes(serverId, mountPoint) {
        const mount = mountPoint.startsWith('/') ? mountPoint.slice(1) : mountPoint;
        return this.request(`/disks/filetypes/${serverId}/${mount}`);
    },

    /**
     * 获取最大文件列表
     */
    async getLargeFiles(serverId, mountPoint, limit = 50) {
        const mount = mountPoint.startsWith('/') ? mountPoint.slice(1) : mountPoint;
        return this.request(`/disks/largefiles/${serverId}/${mount}?limit=${limit}`);
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
};
