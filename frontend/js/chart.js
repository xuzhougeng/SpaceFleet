/**
 * 简易图表模块 - 使用 Canvas 绘制折线图
 */

class SimpleChart {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        this.padding = { top: 40, right: 40, bottom: 60, left: 60 };
        this.data = [];
        this.labels = [];
        
        // 响应式调整
        this.resize();
        window.addEventListener('resize', () => this.resize());
    }

    resize() {
        const container = this.canvas.parentElement;
        const rect = container.getBoundingClientRect();
        
        // 设置高分辨率
        const dpr = window.devicePixelRatio || 1;
        this.canvas.width = rect.width * dpr;
        this.canvas.height = 350 * dpr;
        this.canvas.style.width = rect.width + 'px';
        this.canvas.style.height = '350px';
        this.ctx.scale(dpr, dpr);
        
        this.width = rect.width;
        this.height = 350;
        
        // 重绘
        if (this.data.length > 0) {
            this.draw();
        }
    }

    /**
     * 设置数据并绘制
     * @param {Array} data - 数据点数组 [{date, value, label}]
     * @param {Object} options - 配置选项
     */
    setData(data, options = {}) {
        this.data = data;
        this.options = {
            lineColor: '#3b82f6',
            fillColor: 'rgba(59, 130, 246, 0.1)',
            pointColor: '#3b82f6',
            gridColor: '#e2e8f0',
            textColor: '#64748b',
            title: '',
            yLabel: '',
            yMin: 0,
            yMax: 100,
            ...options,
        };
        this.draw();
    }

    draw() {
        const ctx = this.ctx;
        const { padding, width, height, data, options } = this;
        
        // 清空画布
        ctx.clearRect(0, 0, width, height);
        
        if (data.length === 0) {
            this.drawEmpty();
            return;
        }

        const chartWidth = width - padding.left - padding.right;
        const chartHeight = height - padding.top - padding.bottom;
        
        // 计算数据范围
        const values = data.map(d => d.value);
        const yMin = options.yMin ?? Math.min(...values);
        const yMax = options.yMax ?? Math.max(...values);
        const yRange = yMax - yMin || 1;

        // 绘制网格和Y轴标签
        this.drawGrid(chartWidth, chartHeight, yMin, yMax);
        
        // 绘制标题
        if (options.title) {
            ctx.fillStyle = '#1e293b';
            ctx.font = 'bold 14px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(options.title, width / 2, 20);
        }

        // 计算点坐标
        const points = data.map((d, i) => ({
            x: padding.left + (i / (data.length - 1 || 1)) * chartWidth,
            y: padding.top + chartHeight - ((d.value - yMin) / yRange) * chartHeight,
            data: d,
        }));

        // 绘制填充区域
        ctx.beginPath();
        ctx.moveTo(points[0].x, padding.top + chartHeight);
        points.forEach(p => ctx.lineTo(p.x, p.y));
        ctx.lineTo(points[points.length - 1].x, padding.top + chartHeight);
        ctx.closePath();
        ctx.fillStyle = options.fillColor;
        ctx.fill();

        // 绘制折线
        ctx.beginPath();
        ctx.moveTo(points[0].x, points[0].y);
        points.forEach(p => ctx.lineTo(p.x, p.y));
        ctx.strokeStyle = options.lineColor;
        ctx.lineWidth = 2;
        ctx.stroke();

        // 绘制数据点
        points.forEach(p => {
            ctx.beginPath();
            ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
            ctx.fillStyle = '#fff';
            ctx.fill();
            ctx.strokeStyle = options.pointColor;
            ctx.lineWidth = 2;
            ctx.stroke();
        });

        // 绘制X轴标签（只显示部分）
        const labelStep = Math.ceil(data.length / 8);
        ctx.fillStyle = options.textColor;
        ctx.font = '11px sans-serif';
        ctx.textAlign = 'center';
        
        data.forEach((d, i) => {
            if (i % labelStep === 0 || i === data.length - 1) {
                const x = padding.left + (i / (data.length - 1 || 1)) * chartWidth;
                const label = this.formatDate(d.date);
                ctx.fillText(label, x, height - padding.bottom + 20);
            }
        });
    }

    drawGrid(chartWidth, chartHeight, yMin, yMax) {
        const ctx = this.ctx;
        const { padding, options } = this;
        
        // 绘制5条水平网格线
        const gridLines = 5;
        ctx.strokeStyle = options.gridColor;
        ctx.lineWidth = 1;
        ctx.fillStyle = options.textColor;
        ctx.font = '11px sans-serif';
        ctx.textAlign = 'right';

        for (let i = 0; i <= gridLines; i++) {
            const y = padding.top + (i / gridLines) * chartHeight;
            const value = yMax - (i / gridLines) * (yMax - yMin);
            
            // 网格线
            ctx.beginPath();
            ctx.moveTo(padding.left, y);
            ctx.lineTo(padding.left + chartWidth, y);
            ctx.stroke();
            
            // Y轴标签
            ctx.fillText(value.toFixed(1) + '%', padding.left - 8, y + 4);
        }
    }

    drawEmpty() {
        const ctx = this.ctx;
        ctx.fillStyle = '#64748b';
        ctx.font = '14px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('暂无数据，请选择服务器和挂载点', this.width / 2, this.height / 2);
    }

    formatDate(dateStr) {
        const date = new Date(dateStr);
        return `${date.getMonth() + 1}/${date.getDate()}`;
    }
}

// 全局图表实例
let trendChart = null;

function initChart() {
    trendChart = new SimpleChart('chart-canvas');
}

function updateChart(data, options) {
    if (!trendChart) {
        initChart();
    }
    trendChart.setData(data, options);
}
