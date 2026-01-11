import React, { useEffect, useState, useRef } from 'react';
import { Pause, Terminal, CheckCircle2, Play, HelpCircle } from 'lucide-react';
import api from '../api/client';

export default function Dashboard() {
    const [status, setStatus] = useState(null);
    const [logs, setLogs] = useState([]);
    const logsEndRef = useRef(null);
    const logsContainerRef = useRef(null);
    const [autoScroll, setAutoScroll] = useState(true);
    const [rounds, setRounds] = useState(1);

    useEffect(() => {
        const interval = setInterval(fetchStatus, 1000);
        return () => clearInterval(interval);
    }, []);

    useEffect(() => {
        if (autoScroll && logsEndRef.current) {
            logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [logs, autoScroll]);

    const handleScroll = () => {
        if (logsContainerRef.current) {
            const { scrollTop, scrollHeight, clientHeight } = logsContainerRef.current;
            // If user is near bottom (within 50px), enable auto-scroll
            const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
            setAutoScroll(isAtBottom);
        }
    };

    const fetchStatus = async () => {
        try {
            const res = await api.get('/status');
            setStatus(res.data);
            setLogs(res.data.logs || []);
        } catch (err) {
            console.error("Failed to fetch status", err);
        }
    };

    const handleStop = async () => {
        try {
            await api.post('/control/stop');
        } catch (err) {
            console.error("Failed to stop", err);
        }
    };

    const handleStart = async () => {
        try {
            const res = await api.post('/control/start', { rounds });
            if (res.data.status !== 'success') {
                alert(res.data.message || "启动失败，请先在任务设置中保存配置");
            }
        } catch (err) {
            console.error("Failed to start", err);
            alert("启动请求失败");
        }
    };

    if (!status) return <div className="p-8 text-center text-gray-500">正在连接引擎...</div>;

    const { running, progress } = status;

    return (
        <div className="p-8 max-w-6xl mx-auto h-full flex flex-col">
            <div className="flex justify-between items-center mb-8">
                <div>
                    <h2 className="text-2xl font-bold text-gray-900">运行看板 (Dashboard)</h2>
                    <p className="text-gray-500">{progress.message}</p>
                </div>
                <div className="flex gap-3 items-center">
                    {!running && (
                        <div className="flex items-center gap-2 mr-4 bg-white p-1.5 rounded-lg border border-gray-200 shadow-sm">
                            <label className="text-sm font-medium text-gray-700 ml-2">审查轮次:</label>
                            <input
                                type="number"
                                min="1"
                                max="10"
                                value={rounds}
                                onChange={(e) => setRounds(Math.min(10, Math.max(1, parseInt(e.target.value) || 1)))}
                                className="w-16 px-2 py-1 text-sm border border-gray-300 rounded focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none text-center"
                            />
                            <div className="group relative">
                                <HelpCircle size={16} className="text-gray-400 cursor-help" />
                                <div className="absolute top-full right-0 mt-2 w-64 p-2 bg-gray-800 text-xs text-white rounded shadow-lg opacity-0 group-hover:opacity-100 transition-opacity z-50 pointer-events-none">
                                    多轮审查可提高质量，但过多轮次（&gt;3）可能导致过度修正。建议 1-3 轮。最大 10 轮。
                                </div>
                            </div>
                        </div>
                    )}
                    {running ? (
                        <button onClick={handleStop} className="px-4 py-2 bg-red-50 text-red-600 rounded-lg hover:bg-red-100 font-medium flex items-center gap-2">
                            <Pause size={18} /> 暂停 / 停止
                        </button>
                    ) : (
                        <button onClick={handleStart} className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 font-medium flex items-center gap-2 shadow-sm">
                            <Play size={18} /> 开始审查
                        </button>
                    )}
                </div>
            </div>

            {/* Progress Bar */}
            <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm mb-6">
                <div className="flex justify-between text-sm font-medium text-gray-700 mb-2">
                    <span>总进度</span>
                    <span>{progress.percent}%</span>
                </div>
                <div className="w-full bg-gray-100 rounded-full h-3 overflow-hidden">
                    <div
                        className="bg-indigo-600 h-full rounded-full transition-all duration-500 ease-out"
                        style={{ width: `${progress.percent}%` }}
                    />
                </div>
                <div className="mt-2 text-xs text-gray-500 text-right">
                    已处理 {progress.current} / {progress.total} 条术语
                </div>
            </div>

            {/* Logs Console */}
            <div className="flex-1 bg-gray-900 rounded-xl overflow-hidden flex flex-col shadow-lg border border-gray-800">
                <div className="bg-gray-800 px-4 py-2 flex items-center gap-2 border-b border-gray-700">
                    <Terminal size={16} className="text-gray-400" />
                    <span className="text-xs font-mono text-gray-400">执行日志 (Execution Logs)</span>
                </div>
                <div
                    className="flex-1 p-4 overflow-y-auto font-mono text-sm space-y-1 select-text"
                    onScroll={handleScroll}
                    ref={logsContainerRef}
                >
                    {logs.length === 0 && <div className="text-gray-600 italic">等待日志...</div>}
                    {logs.map((log, i) => (
                        <div key={i} className="text-gray-300 border-l-2 border-transparent hover:border-gray-600 pl-2 whitespace-pre-wrap break-words">
                            {log}
                        </div>
                    ))}
                    <div ref={logsEndRef} />
                </div>
            </div>
        </div>
    );
}
