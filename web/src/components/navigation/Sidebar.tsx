import Logo from "../Logo";
import NavItem from "./NavItem";
import { CameraGroupSelector } from "../filter/CameraGroupSelector";
import { Link, useMatch } from "react-router-dom";
import GeneralSettings from "../menu/GeneralSettings";
import AccountSettings from "../menu/AccountSettings";
import useNavigation from "@/hooks/use-navigation";
import { baseUrl } from "@/api/baseUrl";
import { useMemo } from "react";
import { useBrightness } from "@/context/image-brightness-provider";
import * as SliderPrimitive from "@radix-ui/react-slider";
import { LuSun } from "react-icons/lu";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { TooltipPortal } from "@radix-ui/react-tooltip";

function Sidebar() {
  const basePath = useMemo(() => new URL(baseUrl).pathname, []);
  const { brightness, setBrightness } = useBrightness();

  const isRootMatch = useMatch("/");
  const isBasePathMatch = useMatch(basePath);

  const navbarLinks = useNavigation();

  return (
    <aside className="scrollbar-container scrollbar-hidden absolute inset-y-0 left-0 z-10 flex w-[52px] flex-col justify-between overflow-y-auto border-r border-secondary-highlight bg-background_alt py-4">
      <span tabIndex={0} className="sr-only" />
      <div className="flex w-full flex-col items-center gap-0">
        <Link to="/">
          <Logo className="mb-6 h-8 w-8" />
        </Link>
        {navbarLinks.map((item) => {
          const showCameraGroups =
            (isRootMatch || isBasePathMatch) && item.id === 1;

          return (
            <div key={item.id}>
              <NavItem
                className={`mx-[10px] ${showCameraGroups ? "mb-2" : "mb-4"}`}
                item={item}
                Icon={item.icon}
              />
              {showCameraGroups && <CameraGroupSelector className="mb-4" />}
            </div>
          );
        })}
      </div>
      <div className="mb-8 flex flex-col items-center gap-4">
        <Tooltip>
          <TooltipTrigger asChild>
            <div className="flex flex-col items-center gap-1">
              <LuSun className="size-3 text-muted-foreground" />
              <SliderPrimitive.Root
                orientation="vertical"
                min={30}
                max={1000}
                step={10}
                value={[brightness]}
                onValueChange={(v) => setBrightness(v[0])}
                className="relative flex h-20 touch-none select-none flex-col items-center"
              >
                <SliderPrimitive.Track className="relative w-2 grow overflow-hidden rounded-full bg-secondary">
                  <SliderPrimitive.Range className="absolute w-full bg-primary" />
                </SliderPrimitive.Track>
                <SliderPrimitive.Thumb className="block h-4 w-4 cursor-pointer rounded-full border-2 border-primary bg-background ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2" />
              </SliderPrimitive.Root>
            </div>
          </TooltipTrigger>
          <TooltipPortal>
            <TooltipContent side="right">
              <p>Brightness: {brightness}%</p>
            </TooltipContent>
          </TooltipPortal>
        </Tooltip>
        <GeneralSettings />
        <AccountSettings />
      </div>
    </aside>
  );
}

export default Sidebar;
