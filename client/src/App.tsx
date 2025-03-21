import React, { useState } from 'react';
import './styles/App.css';
import Sidebar from './components/Sidebar.tsx';
import MessageBox from './components/MessageBox.tsx';

function App() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState([]); // Array of messages

  const toggleSidebar = () => {
    setIsSidebarOpen(!isSidebarOpen);
    console.log(isSidebarOpen ? "OPEN" : "CLOSE");
  };

  const createNewChat = () => {
    setMessages([]);
  }

  const handleQueryChange = (e) => {
    setQuery(e.target.value);
  }

  const handleSendMessage = () => {
    if (query.trim() !== '') {
      setMessages([{ text: query, isUser: true }, ...messages]); 
      setQuery('');
    }

      // Simulate AI response with a 0.5-second delay
      setTimeout(() => {
        const aiMessage = { text: "AI isn't implemented yet.", isUser: false };
        setMessages(prevMessages => [aiMessage, ...prevMessages]);
      }, 500); // 500 milliseconds = 0.5 seconds
  };

  return (
    <div className="Home">
      <Sidebar isOpen={isSidebarOpen} toggleSidebar={toggleSidebar} newChat={createNewChat}/>
      <div className="Home-content">
        <div className="chat-content">
          {messages.map((message, index) => (
            <MessageBox key={index} isUserMessage={message.isUser}>
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
    </div>
  );
}

export default App;