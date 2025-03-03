import React from "react";
import '../styles/Sidebar.css'
import {MenuOutlined, EditOutlined} from "@ant-design/icons";

interface SidebarProps {
  isOpen: boolean;
  toggleSidebar: () => void;
}

const Sidebar: React.FC<SidebarProps> = ({ isOpen, toggleSidebar }) => {
  return (
    <div className={`sidebar ${isOpen ? 'open' : ''}`}>
        <div className="sidebar-header">
            <MenuOutlined className="sidebar-icon" onClick={toggleSidebar}/>
            <EditOutlined className="sidebar-icon" />
        </div>
        <div className={`sidebar-content ${isOpen ? "" : "hidden"}`}>
          <div className='past-chats'>
            <span className='time-title'>Yesterday</span>
            <span className='chat-title'>Inventory Mangement Question</span>
          </div>
        </div>
    </div>
    // <div className={`fixed top-0 left-0 h-full bg-gray-800 text-white w-64 transition-transform ${isOpen ? "translate-x-0" : "-translate-x-64"} duration-300`}>
    //   <button className="p-4 text-xl" onClick={toggleSidebar}>✖</button>
    //   <nav className="flex flex-col p-4 space-y-2">
    //     {/* <Link to="/" className="p-2 hover:bg-gray-700 rounded">Home</Link>
    //     <Link to="/about" className="p-2 hover:bg-gray-700 rounded">About</Link>
    //     <Link to="/contact" className="p-2 hover:bg-gray-700 rounded">Contact</Link> */}
    //   </nav>
    // </div>
  );
};

export default Sidebar;
