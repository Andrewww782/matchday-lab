import type { Metadata } from "next";
import { streamlit } from "@/lib/format";

export const metadata: Metadata = { title: "Offside check" };

export default function OffsidePage() {
  return (
    <>
      <h1>
        Offside <em>check</em>
      </h1>
      <p className="lede">
        Draw the lines yourself. Two lines parallel to the goal line meet at the vanishing point, and each player&apos;s offside line runs from his feet to that point. Players are spotted by YOLOX. Your screenshot is not stored.
      </p>
      <p>
        That click-by-click tool stays on the Streamlit app, because it needs the picture model running next to the page. This Vercel site links it rather than pretending the check runs here.
      </p>
      <p>
        <a className="btn" href={streamlit("/offside")}>
          Open the offside check
        </a>
      </p>
      <p className="muted">
        It compares feet in the frame you pick. A real offside decision uses any body part you can score with, at the moment the ball is played.
      </p>
    </>
  );
}
