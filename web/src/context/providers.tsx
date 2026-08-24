import { ReactNode } from "react";
import { ThemeProvider } from "@/context/theme-provider";
import { RecoilRoot } from "recoil";
import { ApiProvider } from "@/api";
import { IconContext } from "react-icons";
import { TooltipProvider } from "@/components/ui/tooltip";
import { StatusBarMessagesProvider } from "@/context/statusbar-provider";
import { LanguageProvider } from "./language-provider";
import { StreamingSettingsProvider } from "./streaming-settings-provider";
import { AuthProvider } from "./auth-context";
import { BrightnessProvider } from "./image-brightness-provider";

type TProvidersProps = {
  children: ReactNode;
};

function providers({ children }: TProvidersProps) {
  return (
    <RecoilRoot>
      <AuthProvider>
        <ApiProvider>
          <ThemeProvider defaultTheme="system" storageKey="frigate-ui-theme">
            <LanguageProvider>
              <TooltipProvider>
                <IconContext.Provider value={{ size: "20" }}>
                  <StatusBarMessagesProvider>
                    <StreamingSettingsProvider>
                      <BrightnessProvider>
                        {children}
                      </BrightnessProvider>
                    </StreamingSettingsProvider>
                  </StatusBarMessagesProvider>
                </IconContext.Provider>
              </TooltipProvider>
            </LanguageProvider>
          </ThemeProvider>
        </ApiProvider>
      </AuthProvider>
    </RecoilRoot>
  );
}

export default providers;
