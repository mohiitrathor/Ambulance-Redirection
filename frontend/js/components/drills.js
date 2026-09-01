/**
 * RAAH Disaster Drills & Stress Testing UI Component (M10 Phase 2)
 * ================================================================
 *
 * Provides drill selection, parameterized casualty surge execution,
 * resilience scoring scorecard rendering, and comparative evaluation.
 * Completely isolated from live command center simulation state.
 */

import { getDrills, runDrill, runStressTest, compareStressTests } from '../api.js';

export class DrillsController {
  constructor() {
    this.selectDrill = document.getElementById('select-drill-name');
    this.inputCasualties = document.getElementById('input-drill-casualties');
    this.inputSeed = document.getElementById('input-drill-seed');
    this.btnRunDrill = document.getElementById('btn-run-drill');
    this.btnRunComparison = document.getElementById('btn-run-drill-compare');
    this.containerResults = document.getElementById('drill-results-container');

    this.init();
  }

  async init() {
    if (!this.selectDrill) return;

    try {
      const drills = await getDrills();
      this.selectDrill.innerHTML = '';
      drills.forEach((d) => {
        const opt = document.createElement('option');
        opt.value = d.name;
        opt.textContent = `${d.title} (${d.category})`;
        this.selectDrill.appendChild(opt);
      });
    } catch (err) {
      console.warn('Could not load drill library in UI:', err);
    }

    if (this.btnRunDrill) {
      this.btnRunDrill.addEventListener('click', () => this.handleRunDrill());
    }
    if (this.btnRunComparison) {
      this.btnRunComparison.addEventListener('click', () => this.handleRunComparison());
    }
  }

  async handleRunDrill() {
    if (!this.selectDrill || !this.btnRunDrill) return;

    const drillName = this.selectDrill.value;
    const seed = parseInt(this.inputSeed?.value || '42', 10);
    const casualties = parseInt(this.inputCasualties?.value || '15', 10);

    this.btnRunDrill.disabled = true;
    this.btnRunDrill.textContent = 'Running Drill...';
    if (this.containerResults) {
      this.containerResults.innerHTML = `<div style="padding: 10px; color: #38bdf8; font-size: 11px; text-align: center;">Executing deterministic drill: <b>${drillName}</b>...</div>`;
    }

    try {
      let result;
      if (drillName === 'CASUALTY_SURGE') {
        result = await runStressTest(casualties, seed);
      } else {
        result = await runDrill(drillName, seed, { casualty_count: casualties });
      }
      this.renderScorecard(result);
    } catch (err) {
      if (this.containerResults) {
        this.containerResults.innerHTML = `<div style="padding: 8px; color: #f87171; font-size: 11px;">Drill execution error: ${err.message}</div>`;
      }
    } finally {
      this.btnRunDrill.disabled = false;
      this.btnRunDrill.textContent = 'Run Drill';
    }
  }

  async handleRunComparison() {
    if (!this.btnRunComparison) return;

    const seed = parseInt(this.inputSeed?.value || '42', 10);

    this.btnRunComparison.disabled = true;
    this.btnRunComparison.textContent = 'Evaluating 25/50/100...';
    if (this.containerResults) {
      this.containerResults.innerHTML = `<div style="padding: 10px; color: #38bdf8; font-size: 11px; text-align: center;">Executing comparative stress benchmarks (25, 50, 100 casualties)...</div>`;
    }

    try {
      const rows = await compareStressTests([25, 50, 100], seed);
      this.renderComparisonTable(rows);
    } catch (err) {
      if (this.containerResults) {
        this.containerResults.innerHTML = `<div style="padding: 8px; color: #f87171; font-size: 11px;">Comparison error: ${err.message}</div>`;
      }
    } finally {
      this.btnRunComparison.disabled = false;
      this.btnRunComparison.textContent = 'Compare 25/50/100';
    }
  }

  renderScorecard(res) {
    if (!this.containerResults) return;

    const rScore = res.resilience_score?.overall || 0;
    const scoreColor = rScore >= 75 ? '#22c55e' : rScore >= 50 ? '#eab308' : '#ef4444';

    this.containerResults.innerHTML = `
      <div style="background: rgba(15, 23, 42, 0.9); border: 1px solid #334155; border-radius: 6px; padding: 10px; font-size: 11px; margin-top: 6px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; border-bottom: 1px solid #334155; padding-bottom: 6px;">
          <div>
            <div style="font-weight: 700; color: #f1f5f9;">${res.drill_name || res.scenario_id}</div>
            <div style="color: #64748b; font-size: 10px;">Hash: ${res.deterministic_hash}</div>
          </div>
          <div style="text-align: right;">
            <div style="font-size: 16px; font-weight: 800; color: ${scoreColor};">${rScore}</div>
            <div style="font-size: 9px; color: #94a3b8; text-transform: uppercase;">Resilience Score</div>
          </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; margin-bottom: 8px;">
          <div style="background: rgba(30, 41, 59, 0.5); padding: 6px; border-radius: 4px;">
            <div style="color: #94a3b8; font-size: 10px;">Dispatched</div>
            <div style="font-size: 12px; font-weight: 700; color: #38bdf8;">${res.incidents_dispatched}/${res.casualty_count} (${res.metrics.fleet_metrics.dispatch_success_ratio_pct}%)</div>
          </div>
          <div style="background: rgba(30, 41, 59, 0.5); padding: 6px; border-radius: 4px;">
            <div style="color: #94a3b8; font-size: 10px;">Average ETA</div>
            <div style="font-size: 12px; font-weight: 700; color: #facc15;">${res.average_response_eta} min</div>
          </div>
          <div style="background: rgba(30, 41, 59, 0.5); padding: 6px; border-radius: 4px;">
            <div style="color: #94a3b8; font-size: 10px;">Hosp. Saturation</div>
            <div style="font-size: 12px; font-weight: 700; color: ${res.hospital_saturation_events > 0 ? '#ef4444' : '#22c55e'};">${res.hospital_saturation_events} Full</div>
          </div>
          <div style="background: rgba(30, 41, 59, 0.5); padding: 6px; border-radius: 4px;">
            <div style="color: #94a3b8; font-size: 10px;">Peak Fleet Utilization</div>
            <div style="font-size: 12px; font-weight: 700; color: #c084fc;">${res.ambulance_utilization}% (${res.max_concurrent_en_route} units)</div>
          </div>
        </div>

        <div style="font-size: 10px; color: #64748b; display: flex; justify-content: space-between;">
          <span>Runtime: ${res.simulation_runtime_ms} ms</span>
          <span>Seed: ${res.seed}</span>
        </div>
      </div>
    `;
  }

  renderComparisonTable(rows) {
    if (!this.containerResults) return;

    let tableRows = rows
      .map(
        (r) => `
        <tr style="border-bottom: 1px solid #334155; font-size: 10px;">
          <td style="padding: 4px 6px; font-weight: 600; color: #f1f5f9;">${r.casualties} Cas</td>
          <td style="padding: 4px 6px; color: #38bdf8;">${r.dispatch_success_pct}%</td>
          <td style="padding: 4px 6px; color: #facc15;">${r.avg_eta_minutes}m</td>
          <td style="padding: 4px 6px; color: ${r.hospital_saturation_count > 0 ? '#ef4444' : '#22c55e'};">${r.hospital_saturation_count}</td>
          <td style="padding: 4px 6px; font-weight: 700; color: ${r.resilience_score >= 60 ? '#22c55e' : '#ef4444'};">${r.resilience_score}</td>
        </tr>
      `
      )
      .join('');

    this.containerResults.innerHTML = `
      <div style="background: rgba(15, 23, 42, 0.9); border: 1px solid #334155; border-radius: 6px; padding: 8px; margin-top: 6px;">
        <div style="font-weight: 700; color: #38bdf8; font-size: 11px; margin-bottom: 6px;">Surge Stress Comparison (25 vs 50 vs 100)</div>
        <table style="width: 100%; border-collapse: collapse; text-align: left;">
          <thead>
            <tr style="border-bottom: 1px solid #475569; color: #94a3b8; font-size: 9px; text-transform: uppercase;">
              <th style="padding: 3px 6px;">Load</th>
              <th style="padding: 3px 6px;">Success</th>
              <th style="padding: 3px 6px;">ETA</th>
              <th style="padding: 3px 6px;">Full</th>
              <th style="padding: 3px 6px;">Resilience</th>
            </tr>
          </thead>
          <tbody>
            ${tableRows}
          </tbody>
        </table>
      </div>
    `;
  }
}
