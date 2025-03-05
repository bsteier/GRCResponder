import React, {useState} from 'react';
import './styles/App.css';
import Sidebar from './components/Sidebar.tsx';
import Tooltip from './components/Tooltip.tsx';

function App() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  const toggleSidebar = () => {
    setIsSidebarOpen(!isSidebarOpen);
    if(isSidebarOpen){
      console.log("OPEN");
    }
    else{
      console.log("CLOSE");
    }
  };

  return (
    <div className="Home">
      <Sidebar isOpen={isSidebarOpen} toggleSidebar={toggleSidebar}/>
      <div className="Home-content">
        <div className="chat-content">
          <p>memo</p>
        </div>
        <input type="text" className="prompt-box" placeholder="Enter a prompt for GRCResponder"/>
      </div>
    </div>
  );
}

export default App;
