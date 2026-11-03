"use client";

// The optional "Cinematic" look: soft contact shadows in corners and under furniture (ambient occlusion), a gentle glow on the few things that
// shine on their own (camera lenses, lights), and a film-style tone curve. It only changes how the scene is drawn, never what it shows.
// It is off by default because it is slower on weak graphics cards.
import React from "react";
import { Bloom, EffectComposer, N8AO, ToneMapping } from "@react-three/postprocessing";
import { ToneMappingMode } from "postprocessing";

export default function CinematicEffects() {
  return (
    <EffectComposer multisampling={0}>
      <N8AO aoRadius={0.9} distanceFalloff={0.6} intensity={2.2} quality="medium" halfRes denoiseSamples={6} denoiseRadius={10} />
      <Bloom intensity={0.45} luminanceThreshold={0.92} luminanceSmoothing={0.2} mipmapBlur />
      <ToneMapping mode={ToneMappingMode.ACES_FILMIC} />
    </EffectComposer>
  );
}
