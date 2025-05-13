import React, {useState, useRef, useEffect} from "react";
import '../styles/Tooltip.css'

interface TooltipProps {
  message: string;
  children: React.ReactNode;
}

const Tooltip: React.FC<TooltipProps> = ({ message, children }) => {
    const [isVisible, setIsVisible] = useState(false);
    const tooltipRef = useRef<HTMLDivElement>(null);
    const [dynamicWidth, setDynamicWidth] = useState('auto');

  useEffect(() => {
    if (isVisible && tooltipRef.current) {
      tooltipRef.current.style.width = 'auto';
      setDynamicWidth(`${tooltipRef.current.offsetWidth}px`);
    } else {
      setDynamicWidth('auto');
    }
  }, [isVisible, message]);

  return (
    <div
      className="tooltip-container"
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
    >
      {children}
      {isVisible && (
        <div
          ref={tooltipRef}
          className="tooltip"
          style={{ width: dynamicWidth }}
        >
          {message}
        </div>
      )}
    </div>

  );
};

export default Tooltip;
