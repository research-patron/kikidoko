import { initializeApp } from "firebase/app";
import { getFirestore } from "firebase/firestore";

const firebaseConfig = {
  apiKey: "AIzaSyBrVNGOTueD6p5RNvsXiggisbETuTrNKbQ",
  authDomain: "kikidoko.firebaseapp.com",
  projectId: "kikidoko",
  storageBucket: "kikidoko.firebasestorage.app",
  messagingSenderId: "644591843641",
  appId: "1:644591843641:web:bee8132cd03284c63bd0e8",
  measurementId: "G-XJ7BS3DS11",
};

const app = initializeApp(firebaseConfig);

export const db = getFirestore(app);
