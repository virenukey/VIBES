import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import logo from "../assets/logo.svg";
import api from "../api/axios";
import loginImage from "../assets/images/login-img.png";

export default function Login() {
  const navigate = useNavigate();

  // Logic States
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [loginSuccess, setLoginSuccess] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  // Redirect if already logged in
  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (token) {
      navigate("/");
    }
  }, [navigate]);

  const handleLogin = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await api.post("/auth/login", { email, password });

      if (res.data.success === true) {
        const { access_token, role, tenant_id, user_id } = res.data.data;

        localStorage.setItem("access_token", access_token);
        localStorage.setItem("role", role);
        localStorage.setItem("tenant_id", tenant_id);
        localStorage.setItem("user_id", user_id);

        setLoginSuccess(true);
        setTimeout(() => {
          navigate("/");
        }, 1200);
      } else {
        setError(res.data.message || "Login failed");
      }
    } catch (err) {
      const errorMessage =
        err.response?.data?.message ||  
        err.response?.data?.detail ||    
        err.response?.data?.error ||     
        (Array.isArray(err.response?.data?.errors)
          ? err.response.data.errors.join(", ")
          : err.response?.data?.errors) || 
        err.message ||               
        "Something went wrong. Try again!";

      setError(errorMessage);
    }
     finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#f1f0ea] flex items-center justify-center p-4 font-sans text-[#1a1a1a]">
      {/* SUCCESS MODAL OVERLAY */}
      {loginSuccess && (
        <div className="fixed inset-0 flex items-center justify-center bg-black/40 backdrop-blur-sm z-50">
          <div className="bg-white rounded-[2rem] shadow-2xl p-8 text-center w-72 animate-in fade-in zoom-in duration-300">
            <div className="flex justify-center mb-4">
              <div className="w-16 h-16 flex items-center justify-center rounded-full bg-green-50">
                <svg
                  className="w-8 h-8 text-green-500"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="3"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M5 13l4 4L19 7"
                  />
                </svg>
              </div>
            </div>
            <h3 className="text-lg font-bold text-gray-800">Welcome Back!</h3>
            <p className="text-xs text-gray-500 mt-2">
              Redirecting to dashboard...
            </p>
          </div>
        </div>
      )}

      {/* MAIN LOGIN CARD - Adjusted to max-w-4xl and fixed height for a smaller look */}
      <div className="w-full max-w-4xl bg-white rounded-[2rem] shadow-2xl overflow-hidden flex flex-col md:flex-row md:h-[560px]">
        {/* LEFT SIDE: IMAGE & TEXT */}
        <div className="relative w-full md:w-1/2 h-48 md:h-auto shrink-0">
          <img
            src={loginImage}
            alt="Kitchen Background"
            className="w-full h-full object-cover"
          />
          <div className="absolute inset-0 bg-black/40"></div>

          <div className="absolute bottom-10 left-8 right-8 text-white">
            <h2 className="text-2xl md:text-4xl font-bold leading-tight tracking-tight">
              Master Your Inventory,
              <br />
            </h2>
            <p className="mt-4 text-sm md:text-lg text-gray-200 max-w-xl leading-snug">
              Precision tracking and automated calculations designed
              specifically for commercial kitchen environments.
            </p>
          </div>
        </div>

        {/* RIGHT SIDE: FORM - Reduced padding to md:p-10 */}
        <div className="w-full md:w-1/2 p-6 md:p-10 flex flex-col justify-center bg-white">
          <div className="flex flex-col items-center text-left mb-8 ml-4">
            {/* Logo + Brand */}
            <div className="flex items-center -mt-16 mr-4">
              <img src={logo} alt="Logo" className="w-52 h-52 object-contain" />
            </div>

            {/* Welcome text */}
            <h2 className="text-2xl font-bold text-gray-900  -mt-8 mr-4">
              Welcome Back
            </h2>

            <p className="text-gray-400 text-xs mt-3 ml-4">
              Enter your credentials to manage your stock levels
            </p>
          </div>

          {/* ERROR MESSAGE */}
          {error && (
            <div className="mb-4 p-3 bg-red-50 border-l-4 border-red-500 text-red-700 text-xs font-medium rounded-r-lg">
              {error}
            </div>
          )}

          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-1.5">
                Email Address
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="chef@vibeskitchen.com"
                className="w-full px-4 py-3 rounded-xl border border-gray-100 focus:ring-2 focus:ring-[#f9a01b] outline-none bg-gray-50/50 transition-all text-sm"
                required
              />
            </div>

            <div>
              <div className="flex justify-between items-center mb-1.5">
                <label className="text-sm font-semibold text-gray-700">
                  Password
                </label>
              </div>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter password"
                  className="w-full px-4 py-3 rounded-xl border border-gray-100 focus:ring-2 focus:ring-[#f9a01b] outline-none bg-gray-50/50 transition-all text-sm"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                >
                  {showPassword ? (
                    <svg
                      className="w-4 h-4"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="M13.875 18.825A10.05 10.05 0 0112 19c-5 0-9.27-3.11-11-7 1.01-2.29 2.87-4.22 5.15-5.36M9.88 9.88a3 3 0 104.24 4.24M3 3l18 18"
                      />
                    </svg>
                  ) : (
                    <svg
                      className="w-4 h-4"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                      />
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="M2.458 12C3.732 7.943 7.523 5 12 5c4.477 0 8.268 2.943 9.542 7-1.274 4.057-5.065 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                      />
                    </svg>
                  )}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-[#FF7300] hover:bg-[#e08e16] disabled:bg-gray-300 text-white py-3.5 rounded-xl font-bold text-sm transition-all shadow-lg shadow-orange-100 flex items-center justify-center gap-2 mt-2"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  Authenticating...
                </span>
              ) : (
                <>Access Dashboard</>
              )}
            </button>

            <p className="text-center text-xs text-gray-400 mt-3">
              Need access?{" "}
              <span className="text-[#FF7300] font-medium cursor-pointer hover:underline">
                Contact your administrator
              </span>
            </p>
          </form>
        </div>
      </div>
    </div>
  );
}
