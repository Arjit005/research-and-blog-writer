import styles from "./research-orb.module.css";

/** Lightweight CSS 3D illustration for the research workspace empty state. */
export function ResearchOrb() {
  return (
    <div className={styles.stage} aria-hidden="true">
      <div className={styles.halo} />
      <div className={styles.orb}>
        <div className={styles.mesh} />
        <div className={styles.core} />
        <span className={styles.orbGlow} />
      </div>
      <div className={`${styles.ring} ${styles.ringOne}`}>
        <span className={styles.node} />
      </div>
      <div className={`${styles.ring} ${styles.ringTwo}`}>
        <span className={`${styles.node} ${styles.nodeMint}`} />
      </div>
      <div className={`${styles.ring} ${styles.ringThree}`} />
      <span className={`${styles.signal} ${styles.signalOne}`} />
      <span className={`${styles.signal} ${styles.signalTwo}`} />
    </div>
  );
}
