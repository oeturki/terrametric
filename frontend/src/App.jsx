import { BrowserRouter, Routes, Route } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Sessions from "./pages/Sessions";
import Plants from "./pages/Plants";
import Reports from "./pages/Reports";
import Login from "./pages/Login";
import AnomalyView from "./components/AnomalyView";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/sessions" element={<Sessions />} />
        <Route path="/plants" element={<Plants />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/login" element={<Login />} />
        <Route path="/anomalies" element={<AnomalyView />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
