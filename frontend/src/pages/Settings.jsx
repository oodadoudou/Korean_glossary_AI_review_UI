
import React, { useEffect, useState } from 'react';
import { Save, Key, Server, Cpu, Eye, EyeOff, Activity } from 'lucide-react';
import api from '../api/client';

export default function SettingsPage() {
    const [config, setConfig] = useState({
        providers: [],
        MAX_WORKERS: 10,
        BATCH_SIZE: 10
    });
    const [saving, setSaving] = useState(false);
    const [testing, setTesting] = useState(false);
    const [message, setMessage] = useState('');
    const [testResults, setTestResults] = useState(null);

    useEffect(() => {
        loadConfig();
    }, []);

    const loadConfig = async () => {
        try {
            const res = await api.get('/config');
            let data = res.data;

            // Backward Compatibility / Migration
            if (!data.providers || data.providers.length === 0) {
                if (data.api_key) {
                    const keys = data.api_key.split('\n').filter(k => k.trim());
                    const newProviders = keys.map(k => ({
                        base_url: data.base_url || '',
                        api_key: k.trim(),
                        model: data.model || 'deepseek-chat'
                    }));
                    data.providers = newProviders;
                } else {
                    data.providers = [{ base_url: '', api_key: '', model: '' }];
                }
            }
            setConfig(data);
        } catch (err) {
            console.error("Failed to load config", err);
        }
    };

    const handleSave = async () => {
        setSaving(true);
        // Ensure legacy fields are synced for compatibility if needed, or just send proper structure
        // Backend handles providers list now.
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
        setTestResults(null);
        try {
            const res = await api.post('/test-connection', config);
            setMessage(res.data.message);
            if (res.data.results) {
                setTestResults(res.data.results);
            }
        } catch (err) {
            setMessage(`❌ 连接错误: ${err.message} `);
        } finally {
            setTesting(false);
        }
    };

    const addProvider = () => {
        setConfig({
            ...config,
            providers: [...config.providers, { base_url: '', api_key: '', model: '' }]
        });
    };

    const removeProvider = (index) => {
        const newProviders = config.providers.filter((_, i) => i !== index);
        setConfig({ ...config, providers: newProviders });
    };

    const updateProvider = (index, field, value) => {
        const newProviders = [...config.providers];
        newProviders[index][field] = value;
        setConfig({ ...config, providers: newProviders });
    };

    return (
        <div className="p-8 max-w-4xl mx-auto">
            <h2 className="text-2xl font-bold text-gray-900 mb-8">系统设置 (Settings)</h2>

            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                <div className="p-6 space-y-8">

                    {/* API Providers Section */}
                    <div>
                        <div className="flex justify-between items-center mb-4">
                            <h3 className="text-lg font-medium text-gray-800 flex items-center gap-2">
                                <Server size={18} /> API 提供商 (Providers)
                            </h3>
                            <button
                                onClick={addProvider}
                                className="px-3 py-1.5 bg-indigo-50 text-indigo-600 rounded-md text-sm font-medium hover:bg-indigo-100 transition-colors"
                            >
                                + 添加提供商
                            </button>
                        </div>

                        <div className="flex gap-2 mb-4">
                            <button
                                onClick={() => {
                                    const newProviders = config.providers.map(p => ({ ...p, enabled: true }));
                                    setConfig({ ...config, providers: newProviders });
                                }}
                                className="text-xs px-2 py-1 bg-gray-100 text-gray-600 rounded hover:bg-gray-200"
                            >
                                全选 (Select All)
                            </button>
                            <button
                                onClick={() => {
                                    const newProviders = config.providers.map(p => ({ ...p, enabled: false }));
                                    setConfig({ ...config, providers: newProviders });
                                }}
                                className="text-xs px-2 py-1 bg-gray-100 text-gray-600 rounded hover:bg-gray-200"
                            >
                                全不选 (Deselect All)
                            </button>
                        </div>

                        <div className="space-y-4">
                            {config.providers && config.providers.map((provider, index) => (
                                <div key={index} className="p-4 border border-gray-200 rounded-lg bg-gray-50 relative group">
                                    <button
                                        onClick={() => removeProvider(index)}
                                        className="absolute top-2 right-2 text-gray-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
                                        title="删除"
                                    >
                                        &times;
                                    </button>

                                    <div className="flex items-start gap-3">
                                        <div className="pt-8">
                                            <input
                                                type="checkbox"
                                                checked={provider.enabled !== false} // Default to true if undefined
                                                onChange={(e) => updateProvider(index, 'enabled', e.target.checked)}
                                                className="w-5 h-5 text-indigo-600 rounded border-gray-300 focus:ring-indigo-500 cursor-pointer"
                                                title={provider.enabled !== false ? "Enabled" : "Disabled"}
                                            />
                                        </div>
                                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 flex-1">
                                            {/* Base URL */}
                                            <div>
                                                <label className="block text-xs font-medium text-gray-500 mb-1">Base URL</label>
                                                <input
                                                    type="text"
                                                    value={provider.base_url}
                                                    onChange={(e) => updateProvider(index, 'base_url', e.target.value)}
                                                    onBlur={(e) => updateProvider(index, 'base_url', e.target.value.trim())}
                                                    placeholder="https://api.openai.com/v1"
                                                    disabled={provider.enabled === false}
                                                    className={`w-full px-3 py-2 border rounded-md text-sm outline-none ${provider.enabled === false ? 'bg-gray-100 text-gray-400 border-gray-200' : 'bg-white border-gray-300 focus:ring-1 focus:ring-indigo-500'}`}
                                                />
                                            </div>

                                            {/* API Key */}
                                            <div>
                                                <label className="block text-xs font-medium text-gray-500 mb-1">API Key</label>
                                                <input
                                                    type="password"
                                                    value={provider.api_key}
                                                    onChange={(e) => updateProvider(index, 'api_key', e.target.value)}
                                                    placeholder="sk-..."
                                                    disabled={provider.enabled === false}
                                                    className={`w-full px-3 py-2 border rounded-md text-sm outline-none font-mono ${provider.enabled === false ? 'bg-gray-100 text-gray-400 border-gray-200' : 'bg-white border-gray-300 focus:ring-1 focus:ring-indigo-500'}`}
                                                />
                                            </div>

                                            {/* Model */}
                                            <div>
                                                <label className="block text-xs font-medium text-gray-500 mb-1">模型名称 (Model)</label>
                                                <input
                                                    type="text"
                                                    value={provider.model}
                                                    onChange={(e) => updateProvider(index, 'model', e.target.value)}
                                                    placeholder="gpt-3.5-turbo"
                                                    disabled={provider.enabled === false}
                                                    className={`w-full px-3 py-2 border rounded-md text-sm outline-none ${provider.enabled === false ? 'bg-gray-100 text-gray-400 border-gray-200' : 'bg-white border-gray-300 focus:ring-1 focus:ring-indigo-500'}`}
                                                />
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            ))}

                            {config.providers && config.providers.length === 0 && (
                                <div className="text-center py-8 text-gray-400 bg-gray-50 rounded-lg border border-dashed border-gray-300">
                                    暂无 API 配置，请点击上方按钮添加。
                                </div>
                            )}
                        </div>
                        <p className="text-xs text-gray-500 mt-2">系统将在每次请求时自动轮询这些可用的 API 提供商。</p>
                    </div>

                    <div className="border-t border-gray-100 my-6"></div>

                    {/* Global Settings */}
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

                    {/* Test Results Display */}
                    {testResults && (
                        <div className="mt-4 border-t pt-4">
                            <h4 className="text-sm font-medium text-gray-700 mb-2">连接测试详情:</h4>
                            <div className="max-h-40 overflow-y-auto space-y-2 bg-gray-50 p-3 rounded-lg">
                                {testResults.map((res, idx) => (
                                    <div key={idx} className="flex flex-col text-xs py-2 border-b border-gray-100 last:border-0">
                                        <div className="flex justify-between items-center w-full">
                                            <span className="font-mono text-gray-600 font-medium">{res.key}</span>
                                            {res.status === 'valid' ? (
                                                <span className="text-green-600 font-medium flex items-center gap-1">✅ OK</span>
                                            ) : (
                                                <span className="text-red-500 font-medium flex items-center gap-1">❌ Failed</span>
                                            )}
                                        </div>
                                        {res.status !== 'valid' && (
                                            <div className="mt-1.5 text-red-600 bg-red-50 p-2 rounded text-xs break-all leading-relaxed">
                                                {res.msg}
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                </div>

                <div className="bg-gray-50 px-6 py-4 flex justify-between items-center border-t border-gray-200">
                    <span className={`text - sm ${message.includes('失败') || message.includes('❌') || message.includes('error') ? 'text-red-600' : (message.includes('⚠️') ? 'text-yellow-600' : 'text-green-600')} `}>
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
