import React, { useState } from 'react';
import '../styles/App.css';
import Sidebar from '../components/Sidebar';
import MessageBox from '../components/MessageBox';
import PdfViewer from '../components/PDFViewer';


function Home() {
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
          {/* <MessageBox files={[]}></MessageBox>
          {messages.map((message, index) => (
            <MessageBox key={index} isUserMessage={message.isUser}>
              {message.text}
            </MessageBox>
          ))} */}
          <MessageBox isUserMessage={false} files={["/Hw2.pdf"]}>
          Lorem ipsum odor amet, consectetuer adipiscing elit. Proin mus vulputate viverra vulputate feugiat ex placerat quam.

Et tempus libero a ut sagittis in vehicula
Nam ultrices semper natoque fames senectus rhoncus:

Neque dolor a fames sollicitudin vivamus mattis magna pharetra. Bibendum lectus per lacinia natoque, at cursus nam morbi. Sed at dis non primis lectus hac arcu platea laoreet sagittis praesent fringilla.
Nascetur per fames mattis inceptos bibendum natoque phasellus metus porttitor. Enim scelerisque vestibulum augue; porttitor metus conubia eleifend inceptos. 
Natoque dui sociosqu, libero ullamcorper inceptos tellus eros cras. 

Facilisi proin sed ultrices taciti fermentum in aliquet nulla class. Nulla varius semper nascetur sociosqu ut. Velit nulla semper semper proin massa porttitor leo.
          </MessageBox>
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