import React, { useEffect, useState } from 'react';
import { FileSpreadsheet, RefreshCw, AlertCircle, Search } from 'lucide-react';
import api from '../api/client';

export default function Results() {
    const [files, setFiles] = useState([]);
    const [selectedFile, setSelectedFile] = useState('');
    const [content, setContent] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [searchTerm, setSearchTerm] = useState('');

    useEffect(() => {
        fetchFiles();
    }, []);

    useEffect(() => {
        if (selectedFile) {
            fetchContent(selectedFile);
        } else {
            setContent([]);
        }
    }, [selectedFile]);

    const fetchFiles = async () => {
        try {
            const res = await api.get('/results/list');
            setFiles(res.data);
            if (res.data.length > 0 && !selectedFile) {
                setSelectedFile(res.data[0]);
            }
        } catch (err) {
            console.error("Failed to fetch files", err);
            setError("无法获取文件列表");
        }
    };

    const fetchContent = async (filename) => {
        setLoading(true);
        setError('');
        try {
            const res = await api.get(`/results/content?filename=${filename}`);
            setContent(res.data);
        } catch (err) {
            console.error("Failed to fetch content", err);
            setError("无法读取文件内容");
            setContent([]);
        } finally {
            setLoading(false);
        }
    };

    const filteredContent = content.filter(row => {
        if (!searchTerm) return true;
        const term = searchTerm.toLowerCase();
        const rowTerm = (row.term || row.korean_term || '').toString().toLowerCase();
        const rowOriginal = (row.original || row.original_translation || '').toString().toLowerCase();
        const rowNew = (row.new || row.recommended_translation || '').toString().toLowerCase();

        return (
            rowTerm.includes(term) ||
            rowOriginal.includes(term) ||
            rowNew.includes(term)
        );
    });

    return (
        <div className="p-8 max-w-7xl mx-auto h-full flex flex-col">
            <div className="flex justify-between items-center mb-6">
                <h2 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
                    <FileSpreadsheet className="text-indigo-600" />
                    审查结果 (Results)
                </h2>
                <button
                    onClick={fetchFiles}
                    className="p-2 text-gray-500 hover:text-indigo-600 transition-colors"
                    title="刷新列表"
                >
                    <RefreshCw size={20} />
                </button>
            </div>

            {/* Controls */}
            <div className="bg-white p-4 rounded-xl border border-gray-200 shadow-sm mb-6 flex gap-4 items-center">
                <div className="flex-1 max-w-xs">
                    <label className="block text-xs font-medium text-gray-500 mb-1">选择文件</label>
                    <select
                        value={selectedFile}
                        onChange={(e) => setSelectedFile(e.target.value)}
                        className="w-full px-3 py-2 bg-gray-50 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                    >
                        {files.length === 0 && <option value="">无结果文件</option>}
                        {files.map(f => <option key={f} value={f}>{f}</option>)}
                    </select>
                </div>

                <div className="flex-1">
                    <label className="block text-xs font-medium text-gray-500 mb-1">搜索术语</label>
                    <div className="relative">
                        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                        <input
                            type="text"
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            placeholder="搜索原文或译文..."
                            className="w-full pl-9 pr-4 py-2 bg-gray-50 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                        />
                    </div>
                </div>
            </div>

            {/* Content Table */}
            <div className="flex-1 bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden flex flex-col">
                {error ? (
                    <div className="flex-1 flex items-center justify-center text-red-500 gap-2">
                        <AlertCircle size={20} />
                        {error}
                    </div>
                ) : loading ? (
                    <div className="flex-1 flex items-center justify-center text-gray-500">
                        加载中...
                    </div>
                ) : content.length === 0 ? (
                    <div className="flex-1 flex items-center justify-center text-gray-400 italic">
                        暂无数据
                    </div>
                ) : (
                    <div className="flex-1 overflow-auto">
                        <table className="w-full text-sm text-left">
                            <thead className="bg-gray-50 text-gray-700 font-medium sticky top-0 z-10">
                                <tr>
                                    <th className="px-4 py-3 border-b">状态</th>
                                    <th className="px-4 py-3 border-b">原文 (Korean)</th>
                                    <th className="px-4 py-3 border-b">原译 (Original)</th>
                                    <th className="px-4 py-3 border-b">建议 (Recommended)</th>
                                    <th className="px-4 py-3 border-b">理由 (Reason)</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100">
                                {filteredContent.map((row, i) => {
                                    // Support both old and new format for backward compatibility if needed, 
                                    // but primarily target the new engine.py JSON format.
                                    const term = row.term || row.korean_term;
                                    const original = row.original || row.original_translation;
                                    const recommended = row.new || row.recommended_translation;
                                    const reason = row.reason || row.deletion_reason;
                                    const justification = row.justification;
                                    const emoji = row.emoji || row.judgment_emoji;
                                    const action = row.action; // 'Delete', 'Modify', 'Keep'

                                    const isDeleted = action === 'Delete' || row.should_delete || emoji === '🗑️';
                                    const isWarning = emoji === '⚠️';

                                    let rowClass = "hover:bg-gray-50";
                                    if (isDeleted) rowClass += " bg-red-50 hover:bg-red-100 text-gray-500";
                                    else if (isWarning) rowClass += " bg-yellow-50 hover:bg-yellow-100";

                                    return (
                                        <tr key={i} className={rowClass}>
                                            <td className="px-4 py-3 text-lg">{emoji}</td>
                                            <td className="px-4 py-3 font-medium">{term}</td>
                                            <td className="px-4 py-3">{original}</td>
                                            <td className="px-4 py-3 font-bold text-indigo-700">
                                                {isDeleted ? <span className="line-through opacity-50">{recommended || original}</span> : recommended}
                                            </td>
                                            <td className="px-4 py-3 text-xs text-gray-600 max-w-xs truncate" title={justification}>
                                                {reason ? <span className="font-bold mr-1">[{reason}]</span> : null}
                                                {justification}
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                )}
                <div className="bg-gray-50 px-4 py-2 border-t border-gray-200 text-xs text-gray-500 flex justify-between">
                    <span>显示 {filteredContent.length} 条结果 (共 {content.length} 条)</span>
                    <span>{selectedFile}</span>
                </div>
            </div>
        </div>
    );
}
