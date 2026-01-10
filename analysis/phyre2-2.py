import React, { useState, useEffect, useRef } from 'react';

const MonitoringSystem = () => {
  // --- AYARLAR ---
  const [targetList, setTargetList] = useState(Array.from({ length: 13 }, (_, i) => `Target ${i + 1}`));
  const [waitDuration, setWaitDuration] = useState(2); // Dakika cinsinden varsayılan süre
  
  // --- DURUM YÖNETİMİ ---
  const [status, setStatus] = useState('IDLE'); // 'IDLE', 'SCANNING', 'WAITING'
  const [currentProcessIndex, setCurrentProcessIndex] = useState(-1); // Hangi target taranıyor?
  const [timeLeft, setTimeLeft] = useState(0); // Geri sayım için saniye
  const [totalWaitTime, setTotalWaitTime] = useState(0); // Yüzdelik bar hesaplamak için

  // --- 1. TARAMA DÖNGÜSÜ (Processing Loop) ---
  const startCycle = async () => {
    setStatus('SCANNING');
    
    // Her bir hedefi tek tek dön
    for (let i = 0; i < targetList.length; i++) {
      setCurrentProcessIndex(i); // UI'da "Şu an bunu tarıyorum" diye göster
      
      // Simülasyon: Her hedef için işlem yapıyormuş gibi bekle (0.5 sn)
      // Buraya gerçek API isteği de gelebilir.
      await new Promise(resolve => setTimeout(resolve, 500)); 
    }

    // Tarama bitti, bekleme moduna geç
    initiateWaiting();
  };

  // --- 2. BEKLEME MODU (Smart Timer) ---
  const initiateWaiting = () => {
    setStatus('WAITING');
    setCurrentProcessIndex(-1); // Seçimi kaldır
    
    // O anki ayarlı süre neyse onu al (Dinamik Süre Mantığı)
    // Kullanıcı input'u değiştirdiyse, bir sonraki döngü o yeni süreyi alır.
    const durationInSeconds = waitDuration * 60; 
    
    setTimeLeft(durationInSeconds);
    setTotalWaitTime(durationInSeconds);
  };

  // --- 3. GERİ SAYIM MANTIĞI (Timer Tick) ---
  useEffect(() => {
    let interval = null;

    if (status === 'WAITING' && timeLeft > 0) {
      // Sadece saniyede bir çalışır, sistemi yormaz.
      interval = setInterval(() => {
        setTimeLeft((prev) => prev - 1);
      }, 1000);
    } else if (status === 'WAITING' && timeLeft === 0) {
      // Süre bitti! Yeni cycle başlat.
      clearInterval(interval);
      startCycle(); 
    }

    return () => clearInterval(interval);
  }, [status, timeLeft]);

  // --- HESAPLAMALAR ---
  // Bekleme yüzdesi (Progress Bar için)
  const waitProgress = totalWaitTime > 0 ? ((totalWaitTime - timeLeft) / totalWaitTime) * 100 : 0;

  return (
    <div className="p-4 border rounded shadow-lg bg-gray-50">
      
      {/* KONTROL PANELİ */}
      <div className="mb-4 flex gap-4 items-center">
        <button 
          onClick={startCycle} 
          disabled={status !== 'IDLE'}
          className="bg-red-600 text-white px-4 py-2 rounded disabled:opacity-50"
        >
          {status === 'IDLE' ? '▶ Initiate Monitoring Loop' : 'System Active...'}
        </button>

        <div className="flex flex-col">
          <label className="text-xs font-bold text-gray-500">Cycle Wait Time (Min)</label>
          <input 
            type="number" 
            value={waitDuration}
            onChange={(e) => setWaitDuration(Number(e.target.value))}
            className="border p-1 rounded w-20"
          />
          <span className="text-xs text-blue-600">
            * Değiştirirseniz bir sonraki döngüde aktif olur.
          </span>
        </div>
      </div>

      {/* DURUM GÖSTERGESİ */}
      
      {/* SENARYO A: TARAMA YAPIYORSA (Download Mode) */}
      {status === 'SCANNING' && (
        <div className="mb-4">
          <h3 className="text-blue-600 font-bold mb-2">Cycle Running: Scanning Targets...</h3>
          <div className="h-4 w-full bg-gray-200 rounded overflow-hidden">
            <div 
              className="h-full bg-blue-500 transition-all duration-300"
              style={{ width: `${((currentProcessIndex + 1) / targetList.length) * 100}%` }}
            ></div>
          </div>
          <p className="text-sm text-right mt-1">{currentProcessIndex + 1} / {targetList.length}</p>
        </div>
      )}

      {/* SENARYO B: BEKLİYORSA (Timer Mode) */}
      {status === 'WAITING' && (
        <div className="mb-4">
          <h3 className="text-orange-600 font-bold mb-2">Cycle Finished. Waiting for next run...</h3>
          
          {/* Yüzdeli Bekleme Animasyonu */}
          <div className="relative h-6 w-full bg-gray-300 rounded overflow-hidden shadow-inner">
            <div 
              className="h-full bg-orange-400 transition-all duration-1000 ease-linear"
              style={{ width: `${waitProgress}%` }}
            ></div>
            <span className="absolute inset-0 flex items-center justify-center text-xs font-bold text-white drop-shadow-md">
              Next Scan in: {Math.floor(timeLeft / 60)}m {timeLeft % 60}s ({Math.floor(waitProgress)}%)
            </span>
          </div>
        </div>
      )}

      {/* HEDEF LİSTESİ GÖRÜNÜMÜ */}
      <div className="grid grid-cols-1 gap-2 border-t pt-4">
        {targetList.map((target, index) => (
          <div 
            key={index} 
            className={`p-2 rounded border flex justify-between items-center transition-colors ${
              index === currentProcessIndex ? 'bg-blue-100 border-blue-500 scale-105 shadow-md' : 'bg-white'
            }`}
          >
            <span>{target}</span>
            {index < currentProcessIndex ? (
              <span className="text-green-500 font-bold">✓ Done</span>
            ) : index === currentProcessIndex ? (
              <span className="text-blue-600 font-bold animate-pulse">Scanning...</span>
            ) : (
              <span className="text-gray-400">Pending</span>
            )}
          </div>
        ))}
      </div>

    </div>
  );
};

export default MonitoringSystem;
