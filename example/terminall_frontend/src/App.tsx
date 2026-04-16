import React, {useState, useCallback} from 'react';
import {Box, Text} from 'ink';
import TextInput from 'ink-text-input';

const API_BASE = process.env.GGBOT_API_URL || 'http://127.0.0.1:8000';

type Message = {role: 'user' | 'assistant' | 'meta' | 'event'; content: string};

const App: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  const processStreamEvent = useCallback((event: any): Message[] => {
    const toAdd: Message[] = [];

    switch (event.type) {
      case 'event':
        // 实时事件
        const evType = event.event_type;
        const deltaText = event?.data?.delta ?? event?.data ?? null;
        const evContent = deltaText ? String(deltaText) : JSON.stringify(event.data);
        toAdd.push({role: 'event', content: `[${evType}] ${evContent}`});
        break;

      case 'error':
        toAdd.push({role: 'assistant', content: `(error) ${event.data?.error}`});
        break;

      case 'complete':
        // 完成事件，单独处理
        const metaParts: string[] = [];
        if (event.data?.session_id) metaParts.push(`session:${event.data.session_id}`);
        if (event.data?.turn_number !== undefined) metaParts.push(`turn:${event.data.turn_number}`);
        if (event.data?.turns_used !== undefined) metaParts.push(`turns_used:${event.data.turns_used}`);
        if (event.data?.title) metaParts.push(`title:${event.data.title}`);
        if (metaParts.length) toAdd.push({role: 'meta', content: metaParts.join(' | ')});

        if (event.data?.final_response) {
          toAdd.push({role: 'assistant', content: String(event.data.final_response)});
        }
        break;
    }

    return toAdd;
  }, []);

  const sendStreaming = async (value: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/messages`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({content: value, stream: true})
      });

      if (!res.body) {
        throw new Error('Response body is not available');
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const {done, value: chunk} = await reader.read();
        if (done) break;

        buffer += decoder.decode(chunk, {stream: true});
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // 保留未完成的行

        for (const line of lines) {
          if (!line.trim()) continue;

          try {
            const data = JSON.parse(line);
            const newMessages = processStreamEvent(data);

            if (newMessages.length > 0) {
              setMessages(prev => [...prev, ...newMessages]);
            }
          } catch (e) {
            console.error('Failed to parse stream line:', line, e);
          }
        }
      }

    } catch (err: any) {
      throw err;
    }
  };

  const sendTraditional = async (value: string) => {
    const res = await fetch(`${API_BASE}/api/v1/messages`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({content: value, stream: false})
    });

    const data = await res.json();
    const toAdd: Message[] = [];

    // 元数据
    const metaParts: string[] = [];
    if (data.session_id) metaParts.push(`session:${data.session_id}`);
    if (data.turn_number !== undefined) metaParts.push(`turn:${data.turn_number}`);
    if (data.turns_used !== undefined) metaParts.push(`turns_used:${data.turns_used}`);
    if (data.title) metaParts.push(`title:${data.title}`);
    if (metaParts.length) toAdd.push({role: 'meta', content: metaParts.join(' | ')});

    // 事件流
    if (Array.isArray(data.events)) {
      for (const ev of data.events) {
        try {
          const evType = ev.type || 'event';
          const deltaText = ev?.data?.delta ?? ev?.data ?? null;
          const evContent = deltaText ? String(deltaText) : JSON.stringify(ev);
          toAdd.push({role: 'event', content: `[${evType}] ${evContent}`});
        } catch (e) {
          toAdd.push({role: 'event', content: JSON.stringify(ev)});
        }
      }
    }

    // 最终响应
    if (data.final_response) {
      toAdd.push({role: 'assistant', content: String(data.final_response)});
    } else if ('answer' in data) {
      toAdd.push({role: 'assistant', content: String((data as any).answer)});
    } else if ('message' in data) {
      toAdd.push({role: 'assistant', content: String((data as any).message)});
    } else if ('result' in data) {
      toAdd.push({role: 'assistant', content: String((data as any).result)});
    } else if (!Array.isArray(data.events)) {
      toAdd.push({role: 'assistant', content: JSON.stringify(data)});
    } else {
      toAdd.push({role: 'assistant', content: String(data)});
    }

    if (toAdd.length > 0) {
      setMessages(prev => [...prev, ...toAdd]);
    }
  };

  const send = useCallback(async (value: string) => {
    if (!value) return;
    setLoading(true);
    setMessages(prev => [...prev, {role: 'user', content: value}]);
    setInput('');

    try {
      // 默认使用流式响应
      await sendStreaming(value);
    } catch (err: any) {
      // 如果流式失败，尝试传统方式
      console.error('Streaming failed, falling back to traditional:', err);
      try {
        await sendTraditional(value);
      } catch (fallbackErr: any) {
        setMessages(prev => [...prev, {role: 'assistant', content: `(error) ${fallbackErr?.message ?? fallbackErr}`}]);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  return (
    React.createElement(Box, {flexDirection: 'column'},
      React.createElement(Box, {flexDirection: 'column', marginBottom: 1},
        messages.map((m, i) => (
          React.createElement(Text, {key: i},
            m.role === 'user' ? `你: ${m.content}` :
            m.role === 'assistant' ? `助: ${m.content}` :
            m.role === 'meta' ? `元: ${m.content}` :
            `evt: ${m.content}`
          )
        ))
      ),
      React.createElement(Box, null,
        React.createElement(Text, null, '输入：'),
        React.createElement(TextInput, {value: input, onChange: setInput, onSubmit: send}),
        loading ? React.createElement(Text, null, ' ⏳') : null
      )
    )
  );
};

export default App;