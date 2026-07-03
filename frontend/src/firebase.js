import { initializeApp } from 'firebase/app';
import { getAuth, GoogleAuthProvider, signInWithPopup, signInWithEmailAndPassword, signOut } from 'firebase/auth';

// Configuracao Firebase (compartilhada com Portal Coherence - mesmo projeto)
const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY || "dummy-key",
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN || "coherence-ominichannel-fs.firebaseapp.com",
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID || "coherence-ominichannel-fs",
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET || "coherence-ominichannel-fs.appspot.com",
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID || "894828119087",
  appId: import.meta.env.VITE_FIREBASE_APP_ID || "1:894828119087:web:3cb2164c2d1efd80e2f2da"
};

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);

export const googleProvider = new GoogleAuthProvider();

export { signInWithPopup, signInWithEmailAndPassword, signOut };
