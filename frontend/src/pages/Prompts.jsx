import React, { useEffect, useState } from 'react';
import { Save, MessageSquare } from 'lucide-react';
import api from '../api/client';

export default function Prompts() {
    const [prompts, setPrompts] = useState({
        batch_review: ''
    });
    const [saving, setSaving] = useState(false);
    const [message, setMessage] = useState('');

    useEffect(() => {
        loadPrompts();
    }, []);

    const loadPrompts = async () => {
        try {
            const res = await api.get('/prompts');
            setPrompts(res.data);
        } catch (err) {
            console.error("Failed to load prompts", err);
        }
    };

    const handleSave = async () => {
        setSaving(true);
        try {
            await api.post('/prompts', prompts);
            setMessage('提示词保存成功');
            setTimeout(() => setMessage(''), 3000);
        } catch (err) {
            setMessage('保存失败');
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="p-8 max-w-4xl mx-auto">
            <h2 className="text-2xl font-bold text-gray-900 mb-8">提示词设置 (Prompts)</h2>

            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                <div className="p-6 space-y-6">

                    {/* Batch Review Prompt */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2 flex items-center gap-2">
                            <MessageSquare size={16} /> 批量审查系统指令 (System Instructions)
                        </label>
                        <p className="text-xs text-gray-500 mb-2">
                            在此处编辑AI的角色设定、核心准则和审查标准。
                            <br />
                            <span className="text-indigo-600">注意：小说背景设定、JSON范例和输出格式将由系统自动追加，无需在此处填写。</span>
                        </p>
                        <textarea
                            value={prompts.batch_review}
                            onChange={(e) => setPrompts({ ...prompts, batch_review: e.target.value })}
                            className="w-full h-96 px-4 py-3 bg-gray-50 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none font-mono text-sm"
                        />
                    </div>

                </div>

                <div className="bg-gray-50 px-6 py-4 flex justify-between items-center border-t border-gray-200">
                    <span className={`text-sm ${message.includes('失败') ? 'text-red-600' : 'text-green-600'}`}>
                        {message}
                    </span>
                    <button
                        onClick={handleSave}
                        disabled={saving}
                        className="px-6 py-2 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 focus:ring-4 focus:ring-indigo-100 transition-all flex items-center gap-2"
                    >
                        <Save size={18} />
                        {saving ? '保存中...' : '保存更改'}
                    </button>
                </div>
            </div>
        </div>
    );
}
