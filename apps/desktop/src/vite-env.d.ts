/// <reference types="vite/client" />

declare module 'three' {
  const THREE: any
  export = THREE
}

declare module 'three/examples/jsm/controls/OrbitControls.js' {
  export const OrbitControls: any
}

declare module 'three/examples/jsm/loaders/GLTFLoader.js' {
  export const GLTFLoader: any
}

declare module 'three/examples/jsm/loaders/OBJLoader.js' {
  export const OBJLoader: any
}
