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



    // --- Playground Logic ---
    const [testTerm, setTestTerm] = useState('이해든');
    const [testTranslation, setTestTranslation] = useState('李海灯');
    const [testContext, setTestContext] = useState('이해든은 말했다.');
    const [testResult, setTestResult] = useState(null);
    const [testing, setTesting] = useState(false);

    const handleTestRun = async () => {
        setTesting(true);
        setTestResult(null);
        try {
            const res = await api.post('/test-prompt', {
                korean_term: testTerm,
                chinese_translation: testTranslation,
                context: testContext,
                custom_prompt: prompts.batch_review // Send current textarea value
            });
            setTestResult(res.data);
        } catch (err) {
            setTestResult({ error: "Testing failed", details: err.message });
        } finally {
            setTesting(false);
        }
    };

    return (
        <div className="p-8 max-w-6xl mx-auto flex gap-6">
            {/* Left Column: Prompt Editor */}
            <div className="flex-1">
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
                                <span className="text-indigo-600">注意：权重分级规则、记忆规则、小说背景设定、JSON范例和输出格式将由系统自动追加，无需在此处填写。</span>
                            </p>
                            <textarea
                                value={prompts.batch_review}
                                onChange={(e) => setPrompts({ ...prompts, batch_review: e.target.value })}
                                className="w-full h-[600px] px-4 py-3 bg-gray-50 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none font-mono text-sm leading-relaxed"
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

            {/* Right Column: Prompt Playground */}
            <div className="w-96 flex flex-col gap-6">
                <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 flex flex-col h-full">
                    <h3 className="text-lg font-bold text-gray-900 mb-4 flex items-center gap-2">
                        🧪 调试台 (Playground)
                    </h3>

                    <div className="space-y-4 flex-1">
                        <div>
                            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">测试术语 (Term)</label>
                            <input
                                type="text"
                                value={testTerm}
                                onChange={(e) => setTestTerm(e.target.value)}
                                className="w-full px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm"
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">当前译文 (Translation)</label>
                            <input
                                type="text"
                                value={testTranslation}
                                onChange={(e) => setTestTranslation(e.target.value)}
                                className="w-full px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm"
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">上下文 (Context)</label>
                            <textarea
                                value={testContext}
                                onChange={(e) => setTestContext(e.target.value)}
                                className="w-full h-24 px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm resize-none"
                            />
                        </div>

                        <button
                            onClick={handleTestRun}
                            disabled={testing}
                            className="w-full py-2 bg-gray-900 text-white rounded-lg font-medium hover:bg-black transition-all disabled:opacity-50"
                        >
                            {testing ? '测试中...' : '运行测试 (Run Test)'}
                        </button>

                        {/* Result Display */}
                        {testResult && (
                            <div className="mt-6 pt-6 border-t border-gray-100 animate-in fade-in slide-in-from-bottom-2">
                                <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">AI 判定结果</label>

                                {testResult.error ? (
                                    <div className="p-3 bg-red-50 text-red-700 rounded-lg text-sm">
                                        ❌ {testResult.error}
                                    </div>
                                ) : (
                                    <div className="space-y-3">
                                        <div className="flex items-center gap-3">
                                            <span className="text-3xl">{testResult.judgment_emoji}</span>
                                            <div>
                                                <div className="text-xs text-gray-500">建议译文</div>
                                                <div className="font-bold text-gray-900 text-lg">
                                                    {testResult.recommended_translation || '(空)'}
                                                </div>
                                            </div>
                                        </div>

                                        {testResult.should_delete && (
                                            <div className="inline-block px-2 py-1 bg-red-100 text-red-700 text-xs rounded font-medium">
                                                🗑️ 建议删除 ({testResult.deletion_reason})
                                            </div>
                                        )}

                                        <div className="bg-gray-50 p-3 rounded-lg border border-gray-100">
                                            <div className="text-xs text-gray-500 mb-1">判定理由 (Reasoning)</div>
                                            <p className="text-sm text-gray-700 leading-relaxed">
                                                {testResult.justification}
                                            </p>
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
