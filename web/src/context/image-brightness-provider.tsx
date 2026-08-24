import { createContext, useContext, useEffect } from "react";
import { useUserPersistence } from "@/hooks/use-user-persistence";

type BrightnessContextType = {
  brightness: number;
  setBrightness: (v: number) => void;
};

const BrightnessContext = createContext<BrightnessContextType | null>(null);

export function BrightnessProvider({ children }: { children: React.ReactNode }) {
  const [brightness, setBrightness] = useUserPersistence("imageBrightness", 100);

  useEffect(() => {
    const value = brightness ?? 100;
    document.documentElement.style.setProperty("--image-brightness", value + "%");
  }, [brightness]);

  return (
    <BrightnessContext.Provider value={{ brightness: brightness ?? 100, setBrightness }}>
      {children}
    </BrightnessContext.Provider>
  );
}

export function useBrightness() {
  const ctx = useContext(BrightnessContext);
  if (!ctx) throw new Error("useBrightness must be used within BrightnessProvider");
  return ctx;
}
