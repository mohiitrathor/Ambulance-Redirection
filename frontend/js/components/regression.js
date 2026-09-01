/**
 * RAAH Continuous Regression Dashboard Controller (M10 Phase 4)
 * =============================================================
 *
 * Runs standardized regression drill suites, compares candidates against
 * official established baselines, evaluates tolerance violations, and displays
 * regression reports.
 *
 * STRICT INVARIANT:
 * Purely observational / isolated execution. Never mutates live simulator.
 */

import * as api from '../api.js';
import { showToast } from './toasts.js';

export class RegressionController {
  constructor() {
    this.dom = {
      txtBaselineVer: document.getElementById('reg-baseline-version'),
      txtCandidateVer: document.getElementById('reg-candidate-version'),
      txtOverallStatus: document.getElementById('reg-overall-status'),
      txtPassedCount: document.getElementById('reg-passed-count'),
      txtWarnedCount: document.getElementById('reg-warned-count'),
      txtFailedCount: document.getElementById('reg-failed-count'),
      tableCasesTbody: document.getElementById('reg-cases-tbody'),
      btnRunSuite: document.getElementById('btn-run-reg-suite'),
      btnCreateBaseline: document.getElementById('btn-create-reg-baseline'),
      btnRun25: document.getElementById('btn-run-reg-25'),
      btnRun50: document.getElementById('btn-run-reg-50'),
      btnRun100: document.getElementById('btn-run-reg-100'),
    };
  }

  init() {
    if (!this.dom.btnRunSuite) return;
    this.bindEvents();
    this.loadBaseline();
  }

  bindEvents() {
    this.dom.btnRunSuite?.addEventListener('click', () => this.runSuite());
    this.dom.btnCreateBaseline?.addEventListener('click', () => this.createBaseline());
    this.dom.btnRun25?.addEventListener('click', () => this.runSurgeDrill(25));
    this.dom.btnRun50?.addEventListener('click', () => this.runSurgeDrill(50));
    this.dom.btnRun100?.addEventListener('click', () => this.runSurgeDrill(100));
  }

  async loadBaseline() {
    try {
      const baseline = await api.getRegressionBaseline();
      if (this.dom.txtBaselineVer) {
        this.dom.txtBaselineVer.textContent = baseline.version || 'unknown';
      }
    } catch (err) {
      if (this.dom.txtBaselineVer) {
        this.dom.txtBaselineVer.textContent = 'None (Action Required)';
      }
    }
  }

  async runSuite() {
    if (this.dom.btnRunSuite) this.dom.btnRunSuite.disabled = true;
    showToast('Executing standard regression drill catalog...', 'info');

    try {
      const report = await api.runRegressionSuite();
      this.renderReport(report);
      showToast(`Regression suite finished: ${report.overall_status}`, report.overall_status === 'PASS' ? 'success' : 'warning');
    } catch (err) {
      showToast(`Regression execution failed: ${err.message}`, 'error');
    } finally {
      if (this.dom.btnRunSuite) this.dom.btnRunSuite.disabled = false;
    }
  }

  async createBaseline() {
    if (this.dom.btnCreateBaseline) this.dom.btnCreateBaseline.disabled = true;
    showToast('Establishing official regression baseline...', 'info');

    try {
      const res = await api.createRegressionBaseline('Official Master Baseline');
      showToast(`Baseline established: ${res.version} (${res.case_count} cases)`, 'success');
      this.loadBaseline();
    } catch (err) {
      showToast(`Failed to create baseline: ${err.message}`, 'error');
    } finally {
      if (this.dom.btnCreateBaseline) this.dom.btnCreateBaseline.disabled = false;
    }
  }

  async runSurgeDrill(count) {
    showToast(`Triggering ${count}-casualty surge stress evaluation...`, 'info');
    try {
      await api.runStressTest(count, 42, 2, false);
      showToast(`${count}-casualty drill run complete. Replay recorded.`, 'success');
    } catch (err) {
      showToast(`Surge run failed: ${err.message}`, 'error');
    }
  }

  renderReport(report) {
    if (!report) return;

    if (this.dom.txtBaselineVer) this.dom.txtBaselineVer.textContent = report.baseline_version;
    if (this.dom.txtCandidateVer) this.dom.txtCandidateVer.textContent = report.candidate_version;
    if (this.dom.txtOverallStatus) {
      this.dom.txtOverallStatus.textContent = report.overall_status;
      this.dom.txtOverallStatus.style.color =
        report.overall_status === 'PASS' ? '#22c55e' :
        report.overall_status === 'WARN' ? '#f59e0b' : '#ef4444';
    }

    if (this.dom.txtPassedCount) this.dom.txtPassedCount.textContent = report.passed_cases;
    if (this.dom.txtWarnedCount) this.dom.txtWarnedCount.textContent = report.warned_cases;
    if (this.dom.txtFailedCount) this.dom.txtFailedCount.textContent = report.failed_cases;

    if (!this.dom.tableCasesTbody) return;
    this.dom.tableCasesTbody.innerHTML = (report.cases || []).map(c => {
      const statusColor = c.status === 'PASS' ? '#22c55e' : c.status === 'WARN' ? '#f59e0b' : '#ef4444';
      const deltaColor = c.delta_resilience >= 0 ? '#22c55e' : '#ef4444';

      return `
        <tr style="border-bottom: 1px solid #1e293b; font-size: 11px;">
          <td style="padding: 6px 8px; font-weight: 700; color: #38bdf8;">${c.scenario_id}</td>
          <td style="padding: 6px 8px;">${c.baseline_resilience}</td>
          <td style="padding: 6px 8px; font-weight: 700;">${c.current_resilience}</td>
          <td style="padding: 6px 8px; font-weight: 800; color: ${deltaColor};">${c.delta_resilience > 0 ? '+' : ''}${c.delta_resilience}</td>
          <td style="padding: 6px 8px; font-family: monospace; font-size: 10px; color: #a5f3fc;">${c.deterministic_hash.slice(0, 10)}</td>
          <td style="padding: 6px 8px; font-weight: 800; color: ${statusColor};">${c.status}</td>
        </tr>
        ${c.violations.length > 0 ? `
          <tr style="background: rgba(239, 68, 68, 0.08); font-size: 10px; color: #fca5a5;">
            <td colspan="6" style="padding: 4px 8px;">⚠️ Violations: ${c.violations.join(' | ')}</td>
          </tr>
        ` : ''}
      `;
    }).join('');
  }
}
