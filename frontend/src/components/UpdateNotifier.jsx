import React, { useState, useEffect } from 'react';
import { Download, RefreshCw, AlertCircle } from 'lucide-react';
import api from '../api/client';

export default function UpdateNotifier() {
    const [currentVersion, setCurrentVersion] = useState('');
    const [updateInfo, setUpdateInfo] = useState(null);
    const [status, setStatus] = useState('idle'); // idle, checking, available, updating, error
    const [errorMsg, setErrorMsg] = useState('');

    useEffect(() => {
        // Fetch current local version
        api.get('/version').then(res => {
            setCurrentVersion(res.data.version);
        }).catch(err => console.error("Failed to fetch version", err));

        // Check for updates
        checkUpdates();
    }, []);

    const checkUpdates = async () => {
        setStatus('checking');
        try {
            const res = await api.get('/check-update');
            if (res.data.is_available) {
                setUpdateInfo(res.data.info);
                setStatus('available');
            } else {
                setStatus('idle');
            }
        } catch (err) {
            console.error("Failed to check for updates", err);
            setStatus('idle');
        }
    };

    const handleUpdate = async () => {
        setStatus('updating');
        try {
            await api.post('/do-update', { download_url: updateInfo.download_url });
            // The process will be killed by the backend, so we expect the request to either hang or fail
            // We can just keep it in updating status
        } catch (err) {
            setStatus('error');
            setErrorMsg(err.message || "更新失败");
        }
    };

    if (status === 'updating') {
        return (
            <div className="p-4 border-t border-orange-200 bg-orange-50 text-xs text-orange-800 flex flex-col gap-2">
                <div className="flex items-center gap-2 font-bold">
                    <RefreshCw className="animate-spin" size={14} />
                    正在下载并更新...
                </div>
                <div className="text-orange-600">
                    请勿关闭应用，应用将自动重启以完成更新。
                </div>
            </div>
        );
    }

    if (status === 'error') {
        return (
            <div className="p-4 border-t border-red-200 bg-red-50 text-xs text-red-800 flex flex-col gap-2">
                <div className="flex items-center gap-2 font-bold">
                    <AlertCircle size={14} />
                    更新失败
                </div>
                <div>{errorMsg}</div>
                <button onClick={() => setStatus('available')} className="underline text-red-600 mt-1">重试</button>
            </div>
        );
    }

    if (status === 'available' && updateInfo) {
        return (
            <div className="p-4 border-t border-indigo-200 bg-indigo-50 text-xs transition-colors">
                <div className="font-bold text-indigo-900 mb-1 flex items-center justify-between">
                    <span>发现新版本 {updateInfo.version}</span>
                    <span className="text-indigo-400 font-normal">当前: {currentVersion}</span>
                </div>

                <button
                    onClick={handleUpdate}
                    className="mt-3 w-full flex items-center justify-center gap-2 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded font-medium transition-colors"
                >
                    <Download size={14} />
                    更新并重启 (Update & Restart)
                </button>
            </div>
        );
    }

    // Default version display
    return (
        <div className="p-4 border-t border-gray-200 flex justify-between items-center text-xs text-gray-500">
            <span>{currentVersion || 'v...'}</span>
            <button
                onClick={checkUpdates}
                disabled={status === 'checking'}
                className="hover:text-indigo-600 transition-colors"
                title="检查更新"
            >
                <RefreshCw size={12} className={status === 'checking' ? 'animate-spin' : ''} />
            </button>
        </div>
    );
}
