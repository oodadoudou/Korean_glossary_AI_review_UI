import React from 'react';
import { ExternalLink, BookOpen, PenTool, Database } from 'lucide-react';

export default function Resources() {
    const resources = [
        {
            title: "LinguaGacha",
            description: "强大的本地化翻译辅助工具，支持多种模型和术语表。",
            url: "https://github.com/neavo/LinguaGacha",
            icon: <PenTool className="w-8 h-8 text-indigo-600" />,
            color: "bg-indigo-50"
        },
        {
            title: "KeywordGacha",
            description: "专业的术语表提取工具，帮助你快速构建项目术语库。",
            url: "https://github.com/neavo/KeywordGacha",
            icon: <Database className="w-8 h-8 text-emerald-600" />,
            color: "bg-emerald-50"
        },
        {
            title: "汉化 Prompt 共享文档",
            description: "金山文档在线协作，查看和分享最新的汉化提示词最佳实践。",
            url: "https://www.kdocs.cn/l/cneDKChuM1Ac",
            icon: <BookOpen className="w-8 h-8 text-amber-600" />,
            color: "bg-amber-50"
        },
        {
            title: "韩语小说汉化指南",
            description: "详细的韩语小说汉化教程，包含从入门到精通的完整指南。",
            url: "https://www.kdocs.cn/l/ce3lO955KwiY",
            icon: <BookOpen className="w-8 h-8 text-blue-600" />,
            color: "bg-blue-50"
        }
    ];

    return (
        <div className="p-8 max-w-5xl mx-auto">
            <h2 className="text-2xl font-bold text-gray-900 mb-8 flex items-center gap-2">
                <BookOpen className="text-indigo-600" />
                资源与工具 (Resources)
            </h2>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {resources.map((item, index) => (
                    <a
                        key={index}
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="block group"
                    >
                        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 h-full transition-all duration-200 hover:shadow-md hover:border-indigo-200 hover:-translate-y-1">
                            <div className={`w-14 h-14 rounded-lg ${item.color} flex items-center justify-center mb-4 group-hover:scale-110 transition-transform`}>
                                {item.icon}
                            </div>
                            <h3 className="text-lg font-bold text-gray-900 mb-2 flex items-center gap-2">
                                {item.title}
                                <ExternalLink size={14} className="text-gray-400 group-hover:text-indigo-500" />
                            </h3>
                            <p className="text-gray-500 text-sm leading-relaxed">
                                {item.description}
                            </p>
                        </div>
                    </a>
                ))}
            </div>

            <div className="mt-12 bg-gray-50 rounded-xl p-6 border border-gray-200">
                <h3 className="text-sm font-bold text-gray-900 mb-2">关于本工具</h3>
                <p className="text-sm text-gray-600">
                    本工具 (Korean Glossary AI Review) 旨在配合上述工具链，提供专业的术语复审功能。
                    建议先使用 KeywordGacha 提取术语，使用 LinguaGacha 进行初翻，最后使用本工具进行批量一致性审查。
                </p>
            </div>
        </div>
    );
}
