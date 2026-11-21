import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'Ash Industry',
  tagline: '여러 AI 에이전트를 한곳에서 띄우고 지켜보고 맡기는 운영 플랫폼',
  favicon: 'img/favicon.svg',
  url: 'https://ash-hun.github.io',
  baseUrl: '/Ash-Industry/',
  organizationName: 'ash-hun',
  projectName: 'Ash-Industry',
  onBrokenLinks: 'throw',
  onBrokenAnchors: 'throw',
  i18n: {defaultLocale: 'ko', locales: ['ko']},
  stylesheets: [
    {
      href: 'https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap',
      type: 'text/css',
    },
    {
      href: 'https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css',
      type: 'text/css',
    },
  ],
  markdown: {mermaid: true},
  themes: ['@docusaurus/theme-mermaid'],
  presets: [
    [
      'classic',
      {
        docs: {
          routeBasePath: '/',
          sidebarPath: './sidebars.ts',
          editUrl: 'https://github.com/ash-hun/Ash-Industry/tree/main/website/',
        },
        blog: false,
        theme: {customCss: './src/css/custom.css'},
      } satisfies Preset.Options,
    ],
  ],
  themeConfig: {
    colorMode: {defaultMode: 'dark', respectPrefersColorScheme: true},
    navbar: {
      title: 'Ash Industry',
      logo: {alt: 'Ash Industry', src: 'img/logo.svg', srcDark: 'img/logo-dark.svg'},
      items: [
        {to: '/intro', label: '시작하기', position: 'left'},
        {to: '/concepts', label: '기능소개', position: 'left'},
        {to: '/agents', label: 'Agent 소개', position: 'left'},
        {to: '/reference', label: '환경설정', position: 'left'},
        {to: '/troubleshooting', label: 'FAQ', position: 'left'},
        {href: 'https://github.com/ash-hun/Ash-Industry', label: 'GitHub', position: 'right'},
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: '문서',
          items: [
            {label: '시작하기', to: '/intro'},
            {label: '기능소개', to: '/concepts'},
            {label: 'Agent 소개', to: '/agents'},
            {label: '환경설정', to: '/reference'},
            {label: 'FAQ', to: '/troubleshooting'},
          ],
        },
        {
          title: '레포',
          items: [
            {label: 'GitHub', href: 'https://github.com/ash-hun/Ash-Industry'},
            {label: 'API 명세', href: 'https://github.com/ash-hun/Ash-Industry/blob/main/docs/api_spec.md'},
            {label: '화면 명세', href: 'https://github.com/ash-hun/Ash-Industry/blob/main/docs/view_spec.md'},
          ],
        },
      ],
      copyright: `Copyright © 2026 ash-hun. Source-available under the PolyForm Noncommercial License 1.0.0; use of this code or docs to train AI models is not permitted.`,
    },
    prism: {theme: prismThemes.github, darkTheme: prismThemes.nightOwl, additionalLanguages: ['bash', 'yaml', 'json']},
    mermaid: {theme: {light: 'neutral', dark: 'dark'}},
  } satisfies Preset.ThemeConfig,
};

export default config;
