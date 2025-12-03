import React, { useState, useEffect } from 'react';
import { FolderOpen, Play, AlertCircle } from 'lucide-react';
import api from '../api/client';

export default function Setup({ onStart }) {
    const [directory, setDirectory] = useState('');
    const [context, setContext] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    useEffect(() => {
        loadSavedConfig();
    }, []);

    const loadSavedConfig = async () => {
        try {
            const res = await api.get('/config');
            if (res.data) {
                if (res.data.last_task_directory) setDirectory(res.data.last_task_directory);
                if (res.data.last_task_context) setContext(res.data.last_task_context);
            }
        } catch (err) {
            console.error("Failed to load config", err);
        }
    };

    const handleSelectFolder = async () => {
        try {
            // Call Python API exposed by pywebview
            if (window.pywebview) {
                const path = await window.pywebview.api.select_folder();
                if (path) {
                    setDirectory(path);
                    validateFolder(path);
                }
            } else {
                // Fallback for browser testing
                const path = prompt("Enter folder path (Browser Mode):");
                if (path) {
                    setDirectory(path);
                    validateFolder(path);
                }
            }
        } catch (err) {
            console.error(err);
            setError("Failed to select folder");
        }
    };

    const validateFolder = async (path) => {
        try {
            const res = await api.post('/check-folder', { path });
            if (!res.data.valid) {
                setError(res.data.error);
            } else {
                setError('');
            }
        } catch (err) {
            setError("Failed to validate folder");
        }
    };

    const handleSaveAndContinue = async () => {
        if (!directory) return;
        setLoading(true);
        try {
            // Save task config to backend
            const res = await api.post('/task/config', { directory, context });
            if (res.data.status === 'success') {
                onStart(); // Navigate to Dashboard
            } else {
                setError("保存配置失败");
            }
        } catch (err) {
            setError("无法连接服务器");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="p-8 max-w-4xl mx-auto">
            <div className="mb-8">
                <h2 className="text-2xl font-bold text-gray-900 mb-2">任务设置</h2>
                <p className="text-gray-500">请选择包含术语表 (.xlsx) 和参考文本 (.txt) 的工作目录，并输入小说背景设定。</p>
            </div>

            <div className="space-y-6">
                {/* Folder Selection */}
                <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
                    <label className="block text-sm font-medium text-gray-700 mb-2">工作目录 (Working Directory)</label>
                    <div className="flex gap-3">
                        <div className="flex-1 px-4 py-2 bg-gray-50 border border-gray-200 rounded-lg text-gray-600 font-mono text-sm flex items-center">
                            {directory || "未选择文件夹"}
                        </div>
                        <button
                            onClick={handleSelectFolder}
                            className="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 font-medium flex items-center gap-2 transition-colors"
                        >
                            <FolderOpen size={18} />
                            浏览...
                        </button>
                    </div>
                    {error && (
                        <div className="mt-2 text-red-600 text-sm flex items-center gap-1">
                            <AlertCircle size={14} />
                            {error}
                        </div>
                    )}
                </div>

                {/* Context Input */}
                <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
                    <label className="block text-sm font-medium text-gray-700 mb-2">小说背景设定 (Context)</label>
                    <textarea
                        value={context}
                        onChange={(e) => setContext(e.target.value)}
                        className="w-full h-40 px-4 py-3 bg-white border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none resize-none text-sm"
                        placeholder="请输入小说背景、角色关系、特殊名词解释等..."
                    />
                </div>

                {/* Action Bar */}
                <div className="flex justify-end pt-4">
                    <button
                        onClick={handleSaveAndContinue}
                        disabled={!directory || !!error || loading}
                        className={`px-8 py-3 bg-indigo-600 text-white rounded-lg font-medium shadow-sm hover:bg-indigo-700 focus:ring-4 focus:ring-indigo-100 transition-all flex items-center gap-2 ${(!directory || !!error || loading) ? 'opacity-50 cursor-not-allowed' : ''
                            }`}
                    >
                        {loading ? '保存中...' : (
                            <>
                                <Play size={20} />
                                保存并继续
                            </>
                        )}
                    </button>
                </div>
            </div>
        </div>
    );
}
