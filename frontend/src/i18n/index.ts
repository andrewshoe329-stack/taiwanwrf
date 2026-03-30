import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from './en.json'
import zh from './zh.json'

const savedLang = localStorage.getItem('tw-forecast-lang')
const validLangs = ['en', 'zh'] as const
const browserLang = navigator.language?.toLowerCase().startsWith('zh') ? 'zh' : 'en'
const initLang = savedLang && validLangs.includes(savedLang as any) ? savedLang : browserLang

i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, zh: { translation: zh } },
  lng: initLang,
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
})

export default i18n
