import React, { useState, useEffect } from 'react';
import '../styles/App.css';
import Sidebar from '../components/Sidebar';
import MessageBox from '../components/MessageBox';
import PdfViewer from '../components/PDFViewer';

const USER_ID = '15';


function Home() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState([]); 
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversationHistory, setConversationHistory] = useState([]);

  useEffect(() => {
    fetchConversations();
  }, []);

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
        text: msg.message,
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

      await fetch(`http://localhost:8000/conversations/${conversationId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sender: "user",
          message: query,
          timestamp: new Date().toISOString()
        })
      });
    } catch (err) {
      console.error("Error saving user message:", err);
    }

    setQuery('');

    setTimeout(async () => {
      const aiMessage = { text: "AI isn't implemented yet.", files: ['/Hw2.pdf'], isUser: false };
      setMessages(prevMessages => [aiMessage, ...prevMessages]);

      try {
        console.log("POSTING MESSAGES");
        await fetch(`http://localhost:8000/conversations/${conversationId}/messages`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            sender: "ai",
            message: aiMessage.text,
            files: aiMessage.files,
            timestamp: new Date().toISOString()
          })
        });
      } catch (err) {
        console.error("Error saving AI message:", err);
      }
    }, 500);
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
      />
      <div className="Home-content">
        <div className="chat-content">
          {messages.map((message, index) => (
            <MessageBox key={index} isUserMessage={message.isUser} files={message.files}>
              {message.text}
            </MessageBox>
          ))}
        </div>
        <input
          type="text"
          className="prompt-box"
          placeholder="Enter a prompt for GRCResponder"
          value={query}
          onChange={handleQueryChange}
          onKeyDown={(e) => {if(e.key === 'Enter'){handleSendMessage()}}}
        />
      </div>
      {/* <PdfViewer  /> */}
    </div>
  );
}

export default Home;