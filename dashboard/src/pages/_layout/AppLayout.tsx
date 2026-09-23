import { Outlet } from "react-router-dom";
import {
  Folder,
  Network,
  Bug,
  FileText,
  BookOpen,
  Terminal,
  Settings,
  Shield,
  Sun,
  Moon,
  CircleUser,
} from "lucide-react";
import { useTheme } from "../../design-system/theme";
import styles from "./AppLayout.module.css";

const NAV = [
  { icon: Folder, label: "Engagements" },
  { icon: Network, label: "Carte de reconnaissance" },
  { icon: Bug, label: "Findings" },
  { icon: FileText, label: "Rapports" },
  { icon: BookOpen, label: "Base de connaissances" },
  { icon: Terminal, label: "DevTools" },
  { icon: Settings, label: "Paramètres" },
  { icon: Shield, label: "Administration" },
];

export function AppLayout(): JSX.Element {
  const { theme, toggle } = useTheme();
  return (
    <div className={styles.app}>
      <aside className={styles.sidebar}>
        <div className={styles.logo}>TEGBESSOU</div>
        <nav className={styles.nav}>
          {NAV.map(({ icon: Icon, label }) => (
            <button key={label} className={styles.navItem} type="button">
              <Icon size={20} />
              <span>{label}</span>
            </button>
          ))}
        </nav>
      </aside>
      <div className={styles.main}>
        <header className={styles.topbar}>
          <span className={styles.crumb}>Tableau de bord</span>
          <div className={styles.actions}>
            <button className={styles.iconBtn} type="button" onClick={toggle} aria-label="Basculer le thème">
              {theme === "dark" ? <Sun size={20} /> : <Moon size={20} />}
            </button>
            <button className={styles.iconBtn} type="button" aria-label="Compte">
              <CircleUser size={20} />
            </button>
          </div>
        </header>
        <section className={styles.content}>
          <Outlet />
        </section>
      </div>
    </div>
  );
}
