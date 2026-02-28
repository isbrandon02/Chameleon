import { Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import ProtectedRoute from "@/components/ProtectedRoute";
import AuthCallback from "@/pages/AuthCallback";
import CompanyBrowse from "@/pages/CompanyBrowse";
import CreatorDashboard from "@/pages/CreatorDashboard";
import Landing from "@/pages/Landing";
import UploadVideo from "@/pages/UploadVideo";
import VideoDetail from "@/pages/VideoDetail";

export default function App() {
  return (
    <>
      <Toaster richColors position="top-right" />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/callback" element={<AuthCallback />} />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute requiredRole="creator">
              <CreatorDashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/upload"
          element={
            <ProtectedRoute requiredRole="creator">
              <UploadVideo />
            </ProtectedRoute>
          }
        />
        <Route
          path="/browse"
          element={
            <ProtectedRoute requiredRole="company">
              <CompanyBrowse />
            </ProtectedRoute>
          }
        />
        <Route
          path="/videos/:videoId"
          element={
            <ProtectedRoute>
              <VideoDetail />
            </ProtectedRoute>
          }
        />
      </Routes>
    </>
  );
}
