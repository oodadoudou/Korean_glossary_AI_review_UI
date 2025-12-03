import React, { useState } from 'react';
import { Settings, FolderOpen, Activity, FileText, MessageSquare, FileSpreadsheet, BookOpen } from 'lucide-react';
import Setup from './pages/Setup';
import Dashboard from './pages/Dashboard';
import SettingsPage from './pages/Settings';
import Prompts from './pages/Prompts';

import Results from './pages/Results';
import Resources from './pages/Resources';

function App() {
    const [activeTab, setActiveTab] = useState('setup');

    const renderContent = () => {
        switch (activeTab) {
            case 'setup': return <Setup onStart={() => setActiveTab('dashboard')} />;
            case 'dashboard': return <Dashboard />;
            case 'results': return <Results />;
            case 'resources': return <Resources />;
            case 'prompts': return <Prompts />;
            case 'settings': return <SettingsPage />;
            default: return <Setup />;
        }
    };

    return (
        <div className="flex h-screen bg-gray-50 text-gray-900 font-sans">
            {/* Sidebar */}
            <div className="w-64 bg-white border-r border-gray-200 flex flex-col">
                <div className="p-6 border-b border-gray-200">
                    <h1 className="text-xl font-bold text-indigo-600 flex items-center gap-2">
                        <Activity className="w-6 h-6" />
                        AI 术语审查
                    </h1>
                </div>

                <nav className="flex-1 p-4 space-y-2">
                    <NavButton
                        active={activeTab === 'setup'}
                        onClick={() => setActiveTab('setup')}
                        icon={<FolderOpen size={20} />}
                        label="任务设置"
                    />
                    <NavButton
                        active={activeTab === 'dashboard'}
                        onClick={() => setActiveTab('dashboard')}
                        icon={<Activity size={20} />}
                        label="运行看板"
                    />
                    <NavButton
                        active={activeTab === 'prompts'}
                        onClick={() => setActiveTab('prompts')}
                        icon={<MessageSquare size={20} />}
                        label="提示词设置"
                    />
                    <NavButton
                        active={activeTab === 'results'}
                        onClick={() => setActiveTab('results')}
                        icon={<FileSpreadsheet size={20} />}
                        label="审查结果"
                    />
                    <NavButton
                        active={activeTab === 'resources'}
                        onClick={() => setActiveTab('resources')}
                        icon={<BookOpen size={20} />}
                        label="资源工具"
                    />
                    <NavButton
                        active={activeTab === 'settings'}
                        onClick={() => setActiveTab('settings')}
                        icon={<Settings size={20} />}
                        label="系统设置"
                    />
                </nav>

                <div className="p-4 border-t border-gray-200 text-xs text-gray-500">
                    v1.0.0
                </div>
            </div>

            {/* Main Content */}
            <div className="flex-1 overflow-auto">
                {renderContent()}
            </div>
        </div>
    );
}

function NavButton({ active, onClick, icon, label }) {
    return (
        <button
            onClick={onClick}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${active
                ? 'bg-indigo-50 text-indigo-700 font-medium'
                : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                }`}
        >
            {icon}
            {label}
        </button>
    );
}

export default App;
