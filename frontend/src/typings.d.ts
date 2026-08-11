declare module '*.png';
declare module '*.jpg';
declare module '*.jpeg';
declare module '*.gif';
declare module '*.svg';
declare module '*.css';
declare module '*.wav';
declare module '*.mp3';
declare module '*.m4a';
declare module '*.rdf';
declare module '*.ttl';
declare module '*.pdf';

interface Window {
  ADMIN_ROLE?: string;
  EXPORT_COMPLIANCE_ROLE?: string;
  AUTH_REALM?: string;
  AUTH_URL?: string;
  AUTH_CLIENTID?: string;
}
