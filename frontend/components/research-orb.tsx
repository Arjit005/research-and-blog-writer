import styles from "./research-orb.module.css";

/** Lightweight CSS 3D illustration for the research workspace empty state. */
export function ResearchOrb() {
  return (
    <div className={styles.stage} aria-hidden="true">
      <div className={styles.halo} />
      <div className={styles.folio}>
        <div className={`${styles.sheet} ${styles.sheetBack}`} />
        <div className={`${styles.sheet} ${styles.sheetMiddle}`} />
        <div className={`${styles.sheet} ${styles.sheetFront}`}>
          <span className={styles.kicker}>FIELD NOTES / 01</span>
          <i className={`${styles.rule} ${styles.ruleLong}`} />
          <i className={`${styles.rule} ${styles.ruleMedium}`} />
          <i className={`${styles.rule} ${styles.ruleShort}`} />
          <span className={styles.diagramLine} />
          <span className={`${styles.source} ${styles.sourceOne}`}>A</span>
          <span className={`${styles.source} ${styles.sourceTwo}`}>B</span>
          <span className={`${styles.source} ${styles.sourceThree}`}>C</span>
        </div>
      </div>
      <span className={`${styles.signal} ${styles.signalOne}`} />
      <span className={`${styles.signal} ${styles.signalTwo}`} />
      <span className={`${styles.signal} ${styles.signalThree}`} />
      <span className={styles.caption}>SOURCE → SYNTHESIS → STORY</span>
    </div>
  );
}
