import { useState, type FormEvent } from "react";
import { Button } from "../../design-system/components/Button";
import styles from "./Login.module.css";

export function Login(): JSX.Element {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  // D0 : aucune connexion réelle. Le câblage à l'API arrive en DASH-1.
  function handleSubmit(e: FormEvent): void {
    e.preventDefault();
  }

  return (
    <div className={styles.wrap}>
      <form className={styles.card} onSubmit={handleSubmit}>
        <h1 className={styles.title}>TEGBESSOU</h1>
        <p className={styles.subtitle}>Connexion</p>
        <label className={styles.label}>
          Email
          <input
            className={styles.input}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="username"
          />
        </label>
        <label className={styles.label}>
          Mot de passe
          <input
            className={styles.input}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </label>
        <Button type="submit">Se connecter</Button>
      </form>
    </div>
  );
}
