import React, { useState, useEffect } from 'react';
import { Eye, EyeOff, Smartphone, Shield, Clock, Users } from 'lucide-react';

const Login = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [currentTime, setCurrentTime] = useState('');

  useEffect(() => {
    // Uhrzeit-Update
    const updateTime = () => {
      const now = new Date();
      setCurrentTime(now.toLocaleTimeString('de-DE', { 
        hour: '2-digit', 
        minute: '2-digit' 
      }));
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  const handleLogin = async () => {
    setIsLoading(true);
    setError('');

    // Simulierte Login-Logik
    setTimeout(() => {
      if (email && password) {
        // Hier würde der echte API-Call stehen
        console.log('Login mit:', email);
        // window.location.href = '/dashboard';
      } else {
        setError('Bitte alle Felder ausfüllen');
      }
      setIsLoading(false);
    }, 1000);
  };

  // Quick-Login für Demo
  const quickLogin = (type) => {
    switch(type) {
      case 'admin':
        setEmail('admin@seda24.de');
        setPassword('admin123');
        break;
      case 'mitarbeiter':
        setEmail('max@seda24.de');
        setPassword('max123');
        break;
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-emerald-50 via-white to-blue-50 flex flex-col">
      {/* Header mit Uhrzeit */}
      <div className="p-4 text-center">
        <div className="text-3xl font-bold text-gray-800">{currentTime}</div>
        <div className="text-sm text-gray-600">
          {new Date().toLocaleDateString('de-DE', { 
            weekday: 'long', 
            day: 'numeric', 
            month: 'long', 
            year: 'numeric' 
          })}
        </div>
      </div>

      {/* Login Container */}
      <div className="flex-1 flex items-center justify-center px-4 pb-20">
        <div className="w-full max-w-md">
          {/* Logo */}
          <div className="text-center mb-8">
            <div className="inline-block bg-white rounded-2xl shadow-lg px-8 py-4 mb-4">
              <h1 className="text-4xl font-black text-emerald-700 tracking-tight">SEDA24</h1>
            </div>
            <p className="text-gray-600 text-lg">Zeiterfassung</p>
          </div>

          {/* Login Form */}
          <div className="bg-white rounded-3xl shadow-xl p-8">
            <div className="space-y-6">
              {/* Email Input */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  E-Mail Adresse
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full px-4 py-4 text-lg border-2 border-gray-200 rounded-xl focus:outline-none focus:border-emerald-500 transition-colors"
                  placeholder="deine.email@seda24.de"
                  autoComplete="email"
                />
              </div>

              {/* Password Input */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Passwort
                </label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full px-4 py-4 text-lg border-2 border-gray-200 rounded-xl focus:outline-none focus:border-emerald-500 transition-colors pr-12"
                    placeholder="••••••••"
                    autoComplete="current-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-4 top-1/2 transform -translate-y-1/2 text-gray-500 hover:text-gray-700"
                  >
                    {showPassword ? <EyeOff size={24} /> : <Eye size={24} />}
                  </button>
                </div>
              </div>

              {/* Error Message */}
              {error && (
                <div className="bg-red-50 text-red-600 px-4 py-3 rounded-lg text-sm">
                  {error}
                </div>
              )}

              {/* Login Button */}
              <button
                onClick={handleLogin}
                disabled={isLoading}
                className={`
                  w-full py-4 rounded-xl font-semibold text-lg transition-all transform
                  ${isLoading 
                    ? 'bg-gray-300 text-gray-500' 
                    : 'bg-gradient-to-r from-emerald-600 to-emerald-700 text-white hover:from-emerald-700 hover:to-emerald-800 hover:shadow-lg active:scale-95'
                  }
                `}
              >
                {isLoading ? (
                  <span className="flex items-center justify-center gap-2">
                    <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                    Anmelden...
                  </span>
                ) : (
                  'Anmelden'
                )}
              </button>
            </div>

            {/* Quick Login für Demo */}
            <div className="mt-6 pt-6 border-t border-gray-200">
              <p className="text-xs text-gray-500 text-center mb-3">Schnell-Login für Demo:</p>
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => quickLogin('admin')}
                  className="px-3 py-2 text-sm bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
                >
                  👨‍💼 Admin
                </button>
                <button
                  onClick={() => quickLogin('mitarbeiter')}
                  className="px-3 py-2 text-sm bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
                >
                  👷 Mitarbeiter
                </button>
              </div>
            </div>
          </div>

          {/* Features */}
          <div className="mt-8 grid grid-cols-3 gap-4 text-center">
            <div className="bg-white/70 backdrop-blur rounded-xl p-3">
              <Shield className="w-6 h-6 mx-auto mb-1 text-emerald-600" />
              <p className="text-xs text-gray-600">SSL Verschlüsselt</p>
            </div>
            <div className="bg-white/70 backdrop-blur rounded-xl p-3">
              <Smartphone className="w-6 h-6 mx-auto mb-1 text-emerald-600" />
              <p className="text-xs text-gray-600">Mobile App</p>
            </div>
            <div className="bg-white/70 backdrop-blur rounded-xl p-3">
              <Clock className="w-6 h-6 mx-auto mb-1 text-emerald-600" />
              <p className="text-xs text-gray-600">24/7 Verfügbar</p>
            </div>
          </div>

          {/* Footer Info */}
          <div className="mt-8 text-center">
            <p className="text-xs text-gray-500">
              Probleme beim Anmelden? 
              <a href="tel:+4972259876" className="text-emerald-600 ml-1">
                📞 07225 9876
              </a>
            </p>
          </div>
        </div>
      </div>

      {/* Bottom Wave Design */}
      <div className="relative">
        <svg className="w-full h-20" viewBox="0 0 1440 120" fill="none">
          <path d="M0,40 C480,120 960,120 1440,40 L1440,120 L0,120 Z" fill="url(#gradient)" />
          <defs>
            <linearGradient id="gradient" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#10b981" stopOpacity="0.1" />
              <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.1" />
            </linearGradient>
          </defs>
        </svg>
      </div>
    </div>
  );
};

export default Login;