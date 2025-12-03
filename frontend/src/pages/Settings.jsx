import React, { useEffect, useState } from 'react';
import { Save, Key, Server, Cpu, Eye, EyeOff, Activity } from 'lucide-react';
import api from '../api/client';

export default function SettingsPage() {
    const [config, setConfig] = useState({
        api_key: '',
        base_url: '',
        model: '',
        MAX_WORKERS: 10,
        BATCH_SIZE: 10
    });
    const [saving, setSaving] = useState(false);
    const [testing, setTesting] = useState(false);
    const [message, setMessage] = useState('');
    const [showApiKey, setShowApiKey] = useState(false);

    useEffect(() => {
        loadConfig();
    }, []);

    const loadConfig = async () => {
        try {
            const res = await api.get('/config');
            setConfig(res.data);
        } catch (err) {
            console.error("Failed to load config", err);
        }
    };

    const handleSave = async () => {
        setSaving(true);
        try {
            await api.post('/config', config);
            setMessage('设置保存成功');
            setTimeout(() => setMessage(''), 3000);
        } catch (err) {
            setMessage('保存失败');
        } finally {
            setSaving(false);
        }
    };

    const handleTestConnection = async () => {
        setTesting(true);
        setMessage('正在测试连接...');
        try {
            const res = await api.post('/test-connection', config);
            if (res.data.status === 'success') {
                setMessage('✅ 连接成功!');
            } else {
                setMessage(`❌ 连接失败: ${res.data.message}`);
            }
        } catch (err) {
            setMessage(`❌ 连接错误: ${err.message}`);
        } finally {
            setTesting(false);
        }
    };

    return (
        <div className="p-8 max-w-3xl mx-auto">
            <h2 className="text-2xl font-bold text-gray-900 mb-8">系统设置 (Settings)</h2>

            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                <div className="p-6 space-y-6">

                    {/* API Key */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2 flex items-center gap-2">
                            <Key size={16} /> API Key
                        </label>
                        <div className="relative">
                            <input
                                type={showApiKey ? "text" : "password"}
                                value={config.api_key}
                                onChange={(e) => setConfig({ ...config, api_key: e.target.value })}
                                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none pr-10"
                            />
                            <button
                                type="button"
                                onClick={() => setShowApiKey(!showApiKey)}
                                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                            >
                                {showApiKey ? <EyeOff size={18} /> : <Eye size={18} />}
                            </button>
                        </div>
                    </div>

                    {/* Base URL */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2 flex items-center gap-2">
                            <Server size={16} /> Base URL
                        </label>
                        <input
                            type="text"
                            value={config.base_url}
                            onChange={(e) => setConfig({ ...config, base_url: e.target.value })}
                            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
                        />
                    </div>

                    {/* Model */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2 flex items-center gap-2">
                            <Cpu size={16} /> 模型名称 (Model Name)
                        </label>
                        <input
                            type="text"
                            value={config.model}
                            onChange={(e) => setConfig({ ...config, model: e.target.value })}
                            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
                        />
                    </div>

                    <div className="grid grid-cols-2 gap-6">
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-2">最大并发数 (Max Workers)</label>
                            <input
                                type="number"
                                value={config.MAX_WORKERS}
                                onChange={(e) => setConfig({ ...config, MAX_WORKERS: parseInt(e.target.value) })}
                                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-2">批处理大小 (Batch Size)</label>
                            <input
                                type="number"
                                value={config.BATCH_SIZE}
                                onChange={(e) => setConfig({ ...config, BATCH_SIZE: parseInt(e.target.value) })}
                                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
                            />
                        </div>
                    </div>

                </div>

                <div className="bg-gray-50 px-6 py-4 flex justify-between items-center border-t border-gray-200">
                    <span className={`text-sm ${message.includes('失败') || message.includes('❌') ? 'text-red-600' : 'text-green-600'}`}>
                        {message}
                    </span>
                    <div className="flex gap-3">
                        <button
                            onClick={handleTestConnection}
                            disabled={testing || saving}
                            className="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg font-medium hover:bg-gray-50 focus:ring-4 focus:ring-gray-100 transition-all flex items-center gap-2"
                        >
                            <Activity size={18} />
                            {testing ? '测试中...' : '测试连接'}
                        </button>
                        <button
                            onClick={handleSave}
                            disabled={saving || testing}
                            className="px-6 py-2 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 focus:ring-4 focus:ring-indigo-100 transition-all flex items-center gap-2"
                        >
                            <Save size={18} />
                            {saving ? '保存中...' : '保存更改'}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
