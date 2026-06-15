import { Link } from "react-router-dom";

export default function HomeCover() {
  return (
    <div className="flex min-h-[calc(100vh-2rem)] w-full items-center justify-center overflow-hidden bg-[#f5fbf8]">
      <div className="relative aspect-[3/2] w-full overflow-hidden">
        <img
          src="/Homepage.png"
          alt="AutoCVE"
          className="h-full w-full select-none object-contain"
          draggable={false}
        />
        <Link
          to="/one-click-cve?start=1"
          aria-label="点击获取CVE编号"
          className="absolute left-[46.3%] top-[58%] h-[9.5%] w-[25.5%] rounded-[999px] outline-none transition focus-visible:ring-4 focus-visible:ring-emerald-400/70"
        />
      </div>
    </div>
  );
}
