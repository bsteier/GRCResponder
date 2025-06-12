import React, { useState, useEffect, useRef } from 'react';
import '../styles/App.css';
import Sidebar from '../components/Sidebar';
import MessageBox from '../components/MessageBox';
import PdfViewer from '../components/PDFViewer';
import { marked } from 'marked';

const USER_ID = '15';


function Home() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState([]); 
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversationHistory, setConversationHistory] = useState([]);
  const bottomRef = useRef(null);

  useEffect(() => {
    fetchConversations();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const fetchConversations = async () => {
    try {
      const res = await fetch(`http://localhost:8000/conversations?user_id=${USER_ID}`);
      if (!res.ok) throw new Error("Failed to fetch conversations");

      const data = await res.json();
      setConversationHistory(data);
    } catch (err) {
      console.error("Error loading conversation history:", err);
    }
  };


  const loadMessages = async (convoId: string) => {
    try {
      const res = await fetch(`http://localhost:8000/conversations/${convoId}/messages`);
      if (!res.ok) throw new Error("Failed to fetch messages");
  
      const data = await res.json();
      console.log(data);
  
      const formattedMessages = data.map(msg => ({
        text: msg.sender === 'user'
          ? msg.message
          : marked(msg.message, {
          breaks: true,
          gfm: true
        }),
        isUser: msg.sender === 'user',
        files: msg.files || []
      }))
        .reverse();
  
      setConversationId(convoId);
      setMessages(formattedMessages);
    } catch (err) {
      console.error("Error loading messages:", err);
    }
  };

  const toggleSidebar = () => {
    setIsSidebarOpen(!isSidebarOpen);
    console.log(isSidebarOpen ? "OPEN" : "CLOSE");

    if (!isSidebarOpen) {
      fetchConversations();
    }
  };

  const createNewChat = async () => {
    try {
      const res = await fetch('http://localhost:8000/conversations', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          user_id: USER_ID,
          timestamp: new Date().toISOString(),
          title: "New Chat"
        })
      });
  
      if (!res.ok) throw new Error("Failed to create conversation");
  
      const data = await res.json();
      setConversationId(data.id);
      setMessages([]);
      fetchConversations();
      return data.id;
    } catch (err) {
      console.error(err);
      return null;
    }
  };
  

  const handleQueryChange = (e) => {
    setQuery(e.target.value);

  const textarea = e.target;
  textarea.style.height = "auto";

  const maxHeight = 120; // e.g., 3-4 lines
  const newHeight = Math.min(textarea.scrollHeight, maxHeight);

  textarea.style.height = `${newHeight}px`;
  }

  const handleSendMessage = async () => {
    if (!query.trim()) return;

    setMessages([{ text: query, isUser: true }, ...messages]);
    let id = conversationId;
    if (!id) {
      id = await createNewChat();
      if (!id) return;
      setConversationId(id);
    }

    try {
      setQuery('');
      const resp = await fetch(`http://localhost:8000/conversations/${conversationId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sender: "user",
          message: query,
          timestamp: new Date().toISOString()
        })
      });
      
      // Get AI Message Response
      const data = await resp.json();
      console.log(data);

      const formattedMessage = marked(data['data']['message'], {
        breaks: true,
        gfm: true
      });

      const aiMessage = { text: formattedMessage, files: ['/me.pdf'], isUser: false };
      console.log(aiMessage);
      setMessages(prevMessages => [aiMessage, ...prevMessages]);
      

    } catch (err) {
      console.error("Error saving user message:", err);
    }
  };

  const handleRenameConversation = async (id: string, newTitle: string) => {
    try {
      await fetch(`http://localhost:8000/conversations/${id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ new_title: newTitle })
      });
      fetchConversations();
    } catch (err) {
      console.error("Error renaming conversation:", err);
    }
  };

  const handleDeleteConversation = async (id: string) => {
    try {
      await fetch(`http://localhost:8000/conversations/${id}`, {
        method: 'DELETE'
      });
      fetchConversations();
      if (id === conversationId) {
        setConversationId(null);
        setMessages([]);
      }
    } catch (err) {
      console.error("Error deleting conversation:", err);
    }
  };

  

  return (
    <div className="Home">
      <Sidebar
        isOpen={isSidebarOpen}
        toggleSidebar={toggleSidebar}
        newChat={createNewChat}
        loadMessages={loadMessages}
        conversationHistory={conversationHistory}
        activeConversationId={conversationId}
        onRenameConversation={handleRenameConversation}
        onDeleteConversation={handleDeleteConversation}
      />
      <div className="Home-content">
        <div className="chat-content">
          {messages.map((message, index) => (
            <MessageBox key={index} isUserMessage={message.isUser} files={message.files}>
              {message.text}
            </MessageBox>
          ))}
        </div>
        <div ref={bottomRef}></div>
        <textarea
          className="prompt-box"
          placeholder="Enter a prompt for GRCResponder"
          value={query}
          onChange={handleQueryChange}
          onKeyDown={(e) => { if (e.key === 'Enter') { handleSendMessage() } }}
          rows={1}
        />
      </div>
      {/* <PdfViewer  /> */}
    </div>
  );
}

export default Home;