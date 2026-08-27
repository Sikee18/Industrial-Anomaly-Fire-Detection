import React, { useState, useRef, useEffect } from 'react';
import { MessageCircle, X, Send, Flame, Loader2, ChevronDown } from 'lucide-react';

const API_URL = 'http://localhost:8000/api';

const QUICK_PROMPTS = [
  "Show me the highest-risk events",
  "What's the most dangerous hotspot?",
  "Are there any persistent sources?",
  "Which industrial facility has the most detections?",
];

export default function PyroChat({ source }) {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: "Hello! I'm **Pyro** 🔥, your Fire Investigation Assistant. I can help you analyze the current thermal anomaly dataset.\n\nTry asking me about specific events, classifications, or risk factors!"
    }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    if (isOpen && messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isOpen]);

  useEffect(() => {
    if (isOpen && inputRef.current) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen]);

  const sendMessage = async (text) => {
    const messageText = text || input.trim();
    if (!messageText || loading) return;

    const userMessage = { role: 'user', content: messageText };
    const newMessages = [...messages, userMessage];
    setMessages(newMessages);
    setInput('');
    setLoading(true);

    try {
      // Build history (exclude the initial system greeting)
      const history = newMessages
        .slice(1) // skip intro message for cleaner context
        .slice(0, -1) // exclude the just-added user msg
        .map(m => ({ role: m.role, content: m.content }));

      const res = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: messageText, source, history }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setMessages(prev => [...prev, { role: 'assistant', content: data.reply }]);
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: "I'm sorry, I couldn't reach the backend. Please ensure the server is running." }]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  // Simple markdown-like formatter
  const formatContent = (content) => {
    return content
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/\n/g, '<br/>');
  };

  return (
    <>
      {/* Floating Button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="fixed bottom-6 right-6 z-[3000] w-14 h-14 rounded-full bg-gradient-to-br from-red-600 to-orange-500 text-white shadow-2xl shadow-red-900/60 hover:scale-110 transition-transform duration-300 flex items-center justify-center group"
          title="Open Pyro Fire Investigation Assistant"
        >
          <Flame className="w-7 h-7 group-hover:animate-pulse" />
        </button>
      )}

      {/* Chat Window */}
      {isOpen && (
        <div className="fixed bottom-6 right-6 z-[3000] w-96 h-[550px] flex flex-col bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl shadow-black/60 overflow-hidden animate-slide-in">
          
          {/* Header */}
          <div className="bg-gradient-to-r from-red-700 via-red-600 to-orange-600 px-4 py-3 flex items-center justify-between shrink-0">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-full bg-white/20 flex items-center justify-center">
                <Flame className="w-4 h-4 text-white" />
              </div>
              <div>
                <h3 className="text-white font-bold text-sm">Pyro</h3>
                <p className="text-red-100 text-xs">Fire Investigation Assistant</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-red-100 bg-red-900/40 px-2 py-0.5 rounded-full border border-red-500/30">
                {source.toUpperCase()}
              </span>
              <button onClick={() => setIsOpen(false)} className="text-white/70 hover:text-white transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-3 space-y-3 custom-scrollbar">
            {messages.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[85%] rounded-xl px-3 py-2 text-sm leading-relaxed ${
                  msg.role === 'user'
                    ? 'bg-blue-600 text-white rounded-br-sm'
                    : 'bg-slate-800 text-slate-100 border border-slate-700 rounded-bl-sm'
                }`}>
                  {msg.role === 'assistant' ? (
                    <div dangerouslySetInnerHTML={{ __html: formatContent(msg.content) }} />
                  ) : (
                    msg.content
                  )}
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex justify-start">
                <div className="bg-slate-800 border border-slate-700 rounded-xl px-4 py-3 flex items-center gap-2">
                  <Loader2 className="w-4 h-4 text-red-400 animate-spin" />
                  <span className="text-slate-400 text-sm">Pyro is analyzing...</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Quick Prompts */}
          <div className="px-3 py-2 flex gap-1.5 overflow-x-auto shrink-0 custom-scrollbar border-t border-slate-800">
            {QUICK_PROMPTS.map((prompt) => (
              <button
                key={prompt}
                onClick={() => sendMessage(prompt)}
                disabled={loading}
                className="whitespace-nowrap text-xs text-slate-300 bg-slate-800 hover:bg-slate-700 border border-slate-700 px-2 py-1.5 rounded-lg transition-colors shrink-0 disabled:opacity-50"
              >
                {prompt}
              </button>
            ))}
          </div>

          {/* Input */}
          <div className="p-3 border-t border-slate-800 flex gap-2 items-end shrink-0">
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about any hotspot or event..."
              rows={1}
              className="flex-1 bg-slate-800 border border-slate-600 focus:border-red-500 text-slate-100 placeholder-slate-500 rounded-xl px-3 py-2 text-sm resize-none focus:outline-none transition-colors max-h-24 custom-scrollbar"
              style={{ minHeight: '38px' }}
            />
            <button
              onClick={() => sendMessage()}
              disabled={!input.trim() || loading}
              className="h-[38px] w-[38px] rounded-xl bg-red-600 hover:bg-red-500 disabled:bg-slate-700 text-white flex items-center justify-center transition-colors shrink-0"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </>
  );
}
