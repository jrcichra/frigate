import { MutableRefObject, useCallback, useEffect, useState } from "react";
import { isDesktop, isMobile } from "react-device-detect";
import { TransformComponent, TransformWrapper } from "react-zoom-pan-pinch";
import VideoControls from "./VideoControls";
import { useOverlayState } from "@/hooks/use-overlay-state";
import { useUserPersistence } from "@/hooks/use-user-persistence";
import { cn } from "@/lib/utils";
import { ASPECT_VERTICAL_LAYOUT } from "@/types/record";
import { Slider } from "@/components/ui/slider";
import { LuDownload } from "react-icons/lu";

type ExportVideoPlayerProps = {
  videoRef: MutableRefObject<HTMLVideoElement | null>;
  source: string;
  downloadName?: string;
};

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) {
    return "0:00";
  }

  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) {
    return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  return `${m}:${String(s).padStart(2, "0")}`;
}

export default function ExportVideoPlayer({
  videoRef,
  source,
  downloadName,
}: ExportVideoPlayerProps) {
  const [loadedMetadata, setLoadedMetadata] = useState(false);
  const [tallCamera, setTallCamera] = useState(false);
  const [isPlaying, setIsPlaying] = useState(true);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [muted, setMuted] = useUserPersistence("hlsPlayerMuted", true);
  const [volume, setVolume] = useOverlayState("playerVolume", 1.0);
  const [defaultPlaybackRate] = useUserPersistence("playbackRate", 1);
  const [playbackRate, setPlaybackRate] = useOverlayState(
    "playbackRate",
    defaultPlaybackRate ?? 1,
  );
  const [mobileCtrlTimeout, setMobileCtrlTimeout] = useState<NodeJS.Timeout>();
  const [controls, setControls] = useState(isMobile);
  const [controlsOpen, setControlsOpen] = useState(false);
  const [zoomScale, setZoomScale] = useState(1.0);
  const seekDuration = Number.isFinite(duration) && duration > 0 ? duration : 0;

  useEffect(() => {
    if (!videoRef.current) {
      return;
    }
    setLoadedMetadata(false);
    setCurrentTime(0);
    setDuration(0);
    videoRef.current.src = source;
    videoRef.current.load();
  }, [videoRef, source]);

  useEffect(() => {
    if (!isDesktop) {
      return;
    }

    const callback = (e: MouseEvent) => {
      if (!videoRef.current) {
        return;
      }

      const rect = videoRef.current.getBoundingClientRect();
      if (
        e.clientX > rect.left &&
        e.clientX < rect.right &&
        e.clientY > rect.top &&
        e.clientY < rect.bottom
      ) {
        setControls(true);
      } else {
        setControls(controlsOpen);
      }
    };

    window.addEventListener("mousemove", callback);
    return () => window.removeEventListener("mousemove", callback);
  }, [videoRef, controlsOpen]);

  const onPlayPause = useCallback(
    (play: boolean) => {
      if (!videoRef.current) {
        return;
      }

      if (play) {
        videoRef.current.play();
      } else {
        videoRef.current.pause();
      }
    },
    [videoRef],
  );

  const onSeek = useCallback(
    (diff: number) => {
      if (!videoRef.current) {
        return;
      }

      videoRef.current.currentTime = Math.max(
        0,
        videoRef.current.currentTime + diff,
      );
    },
    [videoRef],
  );

  const showControls = controls || controlsOpen;

  return (
    <TransformWrapper
      minScale={1.0}
      wheel={{ smoothStep: 0.005 }}
      onZoom={(zoom) => setZoomScale(zoom.state.scale)}
    >
      {showControls && (
        <div
          className={cn(
            "absolute left-1/2 z-50 flex w-[90%] -translate-x-1/2 flex-col gap-2",
            tallCamera ? "bottom-14" : "bottom-7",
          )}
        >
          <div className="flex items-center gap-2 text-xs text-white">
            <span className="tabular-nums">{formatTime(currentTime)}</span>
            <Slider
              className="flex-1"
              min={0}
              max={seekDuration || 1}
              step={0.1}
              value={[Math.min(currentTime, seekDuration || 1)]}
              disabled={!seekDuration}
              onValueChange={([val]) => {
                if (videoRef.current) {
                  videoRef.current.currentTime = val;
                  setCurrentTime(val);
                }
              }}
            />
            <span className="tabular-nums">{formatTime(duration)}</span>
            <a
              href={source}
              download={downloadName ?? true}
              aria-label="Download export"
              className="ml-1 flex size-6 shrink-0 cursor-pointer items-center justify-center rounded-full bg-black/50 text-white hover:bg-black/70 hover:text-primary"
              onClick={(e) => e.stopPropagation()}
            >
              <LuDownload className="size-4" />
            </a>
          </div>
          <div className="flex justify-center">
            <VideoControls
              video={videoRef.current}
              isPlaying={isPlaying}
              show
              muted={muted}
              volume={volume}
              features={{
                volume: true,
                seek: true,
                playbackRate: true,
                plusUpload: false,
                fullscreen: false,
              }}
              setControlsOpen={setControlsOpen}
              setMuted={(m) => setMuted(m)}
              playbackRate={playbackRate ?? 1}
              hotKeys
              onPlayPause={onPlayPause}
              onSeek={onSeek}
              onSetPlaybackRate={(rate) => {
                setPlaybackRate(rate, true);

                if (videoRef.current) {
                  videoRef.current.playbackRate = rate;
                }
              }}
            />
          </div>
        </div>
      )}
      <TransformComponent
        wrapperStyle={{ width: "100%", height: "100%" }}
        wrapperProps={{
          onClick: isDesktop ? undefined : () => setControls(!controls),
        }}
        contentStyle={{ width: "100%", height: isMobile ? "100%" : undefined }}
      >
        <video
          ref={videoRef}
          className={`size-full rounded-lg bg-black md:rounded-2xl cursor-pointer ${loadedMetadata ? "" : "invisible"}`}
          preload="auto"
          autoPlay
          playsInline
          muted={muted}
          onClick={
            isDesktop
              ? () => {
                  if (zoomScale === 1.0) {
                    onPlayPause(!isPlaying);
                  }
                }
              : undefined
          }
          onVolumeChange={() => {
            setVolume(videoRef.current?.volume ?? 1.0, true);
          }}
          onPlay={() => {
            setIsPlaying(true);

            if (isMobile) {
              setControls(true);
              setMobileCtrlTimeout(setTimeout(() => setControls(false), 4000));
            }
          }}
          onPause={() => {
            setIsPlaying(false);

            if (isMobile && mobileCtrlTimeout) {
              clearTimeout(mobileCtrlTimeout);
            }
          }}
          onTimeUpdate={() => {
            setCurrentTime(videoRef.current?.currentTime ?? 0);
          }}
          onLoadedMetadata={() => {
            setLoadedMetadata(true);

            if (!videoRef.current) {
              return;
            }

            const w = videoRef.current.videoWidth;
            const h = videoRef.current.videoHeight;

            if (h > 0) {
              setTallCamera(w / h < ASPECT_VERTICAL_LAYOUT);
            }

            setDuration(videoRef.current.duration || 0);

            if (playbackRate) {
              videoRef.current.playbackRate = playbackRate;
            }

            if (volume) {
              videoRef.current.volume = volume;
            }
          }}
        />
      </TransformComponent>
    </TransformWrapper>
  );
}
