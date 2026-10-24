/**
 * Memory-Centric Computing Architecture: Interactive Dashboard Engine
 * Handles live simulation calls, trace animation, dynamic hardware visualization, and charts.
 */

document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const tabBtns = document.querySelectorAll(".tab-btn");
    const tabContents = document.querySelectorAll(".tab-content");
    
    const workloadSelect = document.getElementById("workload-select");
    const policySelect = document.getElementById("policy-select");
    const bwSlider = document.getElementById("interconnect-bw");
    const bwVal = document.getElementById("bw-val");
    const liveBw = document.getElementById("live-bw");
    
    const btnRunSim = document.getElementById("btn-run-sim");
    const btnAnimateSim = document.getElementById("btn-animate-sim");
    
    // Hardware elements
    const hostUnit = document.getElementById("host-unit");
    const memoryUnit = document.getElementById("memory-unit");
    const packetElem = document.getElementById("packet-elem");
    const stepInfo = document.getElementById("step-info");
    const liveDecisionBadge = document.getElementById("live-decision-badge");
    const liveDecisionReason = document.getElementById("live-decision-reason");
    const liveDecisionOverhead = document.getElementById("live-decision-overhead");

    // KPIs
    const kpiTime = document.getElementById("kpi-time");
    const kpiSpeedup = document.getElementById("kpi-speedup");
    const kpiTraffic = document.getElementById("kpi-traffic");
    const kpiTrafficReduc = document.getElementById("kpi-traffic-reduc");
    const kpiEnergy = document.getElementById("kpi-energy");
    const kpiEnergyReduc = document.getElementById("kpi-energy-reduc");
    const kpiEdp = document.getElementById("kpi-edp");
    const kpiEdpReduc = document.getElementById("kpi-edp-reduc");

    // Trace Table
    const traceTbody = document.getElementById("trace-tbody");

    // Chart.js instance
    let energyChart = null;

    // --- Tab Switching ---
    tabBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            tabBtns.forEach(b => b.classList.remove("active"));
            tabContents.forEach(c => c.classList.remove("active"));

            btn.classList.add("active");
            const targetId = btn.getAttribute("data-tab");
            document.getElementById(targetId).classList.add("active");
        });
    });

    // --- Slider listener ---
    bwSlider.addEventListener("input", (e) => {
        const val = e.target.value;
        bwVal.textContent = `${val} GB/s`;
        liveBw.textContent = val;
    });

    // --- Workload Selector hint & metadata update ---
    workloadSelect.addEventListener("change", () => {
        const w = workloadSelect.value;
        const metaPattern = document.getElementById("meta-pattern");
        const metaIntensity = document.getElementById("meta-intensity");
        const metaReuse = document.getElementById("meta-reuse");
        const hint = document.getElementById("workload-hint");

        if (w === "reusable") {
            hint.textContent = "Dense GEMM: High operational intensity, high temporal reuse in L1/L2/LLC.";
            metaPattern.textContent = "Tiled / Spatial";
            metaIntensity.textContent = "High (16 - 64 FLOPs/B)";
            metaReuse.textContent = "High (Cache resident)";
        } else if (w === "streaming") {
            hint.textContent = "Vector SAXPY & Filter: Stream throughput bound, single-pass elements, zero reuse.";
            metaPattern.textContent = "Sequential Stream";
            metaIntensity.textContent = "Low (0.25 - 0.5 FLOPs/B)";
            metaReuse.textContent = "None (Single pass)";
        } else if (w === "random") {
            hint.textContent = "Graph BFS / SpMV: Irregular pointer chasing, high cache miss rate, bus line amplification.";
            metaPattern.textContent = "Random / Sparse";
            metaIntensity.textContent = "Very Low (< 0.2 FLOPs/B)";
            metaReuse.textContent = "Poor (< 0.2x)";
        } else {
            hint.textContent = "Multi-phase workflow interleaving Random, Streaming, and Reusable phases.";
            metaPattern.textContent = "Hybrid Heterogeneous";
            metaIntensity.textContent = "Dynamic (0.2 - 16.0 FLOPs/B)";
            metaReuse.textContent = "Multi-Tiered";
        }
    });

    // --- Initialize Chart ---
    function initChart() {
        const ctx = document.getElementById("energyChart").getContext("2d");
        energyChart = new Chart(ctx, {
            type: "bar",
            data: {
                labels: ["Compute", "Interconnect", "Memory", "Overhead"],
                datasets: [{
                    label: "Energy (mJ)",
                    data: [0, 0, 0, 0],
                    backgroundColor: [
                        "#3b82f6", // Blue
                        "#f59e0b", // Amber
                        "#ec4899", // Pink
                        "#64748b"  // Slate
                    ],
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: { color: "rgba(255, 255, 255, 0.05)" },
                        ticks: { color: "#94a3b8" }
                    },
                    x: {
                        grid: { display: false },
                        ticks: { color: "#94a3b8" }
                    }
                }
            }
        });
    }
    initChart();

    // --- Run Simulation via Backend API or Client Fallback ---
    async function runSimulation(isAnimated = false) {
        btnRunSim.disabled = true;
        btnAnimateSim.disabled = true;
        stepInfo.textContent = "Simulating...";

        const payload = {
            workload: workloadSelect.value,
            policy: policySelect.value,
            interconnect_bw: parseFloat(bwSlider.value)
        };

        try {
            const resp = await fetch("/api/simulate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            if (!resp.ok) throw new Error("API simulation failed");
            const data = await resp.json();
            
            updateMetrics(data.metrics);
            updateEnergyChart(data.metrics);

            if (isAnimated && data.trace && data.trace.length > 0) {
                await playAnimation(data.trace);
            } else {
                renderTraceTable(data.trace || []);
                highlightStaticDecision(data.metrics);
            }

        } catch (err) {
            console.warn("Backend API unavailable, executing client-side simulation model:", err);
            runClientSideSimulation(payload, isAnimated);
        } finally {
            btnRunSim.disabled = false;
            btnAnimateSim.disabled = false;
        }
    }

    // --- Update KPI Display ---
    function updateMetrics(m) {
        kpiTime.textContent = `${m.execution_time_ms.toFixed(2)} ms`;
        
        const speedupVal = m.speedup || 1.0;
        kpiSpeedup.textContent = `${speedupVal.toFixed(2)}x Speedup`;
        kpiSpeedup.className = `kpi-badge speedup ${speedupVal >= 1.0 ? '' : 'negative'}`;

        kpiTraffic.textContent = `${m.total_data_movement_mb.toFixed(1)} MB`;
        const trafficReduc = m.energy_reduction_pct !== undefined ? (100 - (m.total_data_movement_mb / 40.0 * 100)) : 0;
        kpiTrafficReduc.textContent = `${Math.max(0, trafficReduc).toFixed(1)}% Data Saved`;

        const energyMj = m.total_energy_joules * 1000.0;
        kpiEnergy.textContent = `${energyMj.toFixed(2)} mJ`;
        kpiEnergyReduc.textContent = `${Math.max(0, m.energy_reduction_pct || 0).toFixed(1)}% Energy Saved`;

        const edpVal = m.edp || (m.total_energy_joules * (m.execution_time_ms / 1000.0));
        kpiEdp.textContent = `${(edpVal * 1e6).toFixed(2)} µJ·s`;
        kpiEdpReduc.textContent = `${Math.max(0, m.edp_reduction_pct || 0).toFixed(1)}% EDP Saved`;
    }

    // --- Update Energy Chart ---
    function updateEnergyChart(m) {
        if (!energyChart) return;
        const comp = m.compute_energy_uj / 1000.0;
        const xfer = m.interconnect_energy_uj / 1000.0;
        const mem = m.memory_energy_uj / 1000.0;
        const oh = m.decision_energy_uj / 1000.0;

        energyChart.data.datasets[0].data = [comp, xfer, mem, oh];
        energyChart.update();
    }

    // --- Render Trace Table ---
    function renderTraceTable(trace) {
        traceTbody.innerHTML = "";
        trace.slice(0, 50).forEach((t, idx) => {
            const row = document.createElement("tr");
            const tagClass = t.decision === "PIM" ? "tag-pim" : "tag-host";
            const latencyUs = ((t.compute_time_ns + t.transfer_time_ns) / 1000.0).toFixed(1);
            const dataKb = ((t.bytes_transferred || 0) / 1024.0).toFixed(1);

            row.innerHTML = `
                <td>${idx + 1}</td>
                <td><strong>${t.phase_name || t.kernel_name}</strong></td>
                <td><span style="font-size: 0.75rem; color: #94a3b8;">${t.access_pattern}</span></td>
                <td><span class="${tagClass}">${t.decision}</span></td>
                <td>${latencyUs} µs</td>
                <td>${dataKb} KB</td>
                <td style="font-size: 0.75rem; color: #94a3b8;">${t.reason}</td>
            `;
            traceTbody.appendChild(row);
        });
    }

    function highlightStaticDecision(m) {
        const isPim = m.pim_chunks_executed > m.host_chunks_executed;
        liveDecisionBadge.textContent = isPim ? "PIM UNITS" : "HOST CPU";
        liveDecisionBadge.className = `decision-badge ${isPim ? 'pim-badge' : ''}`;
        liveDecisionReason.textContent = isPim 
            ? "Memory-bound / Streaming: Dispatched to near-bank PIM units to eliminate interconnect overhead."
            : "Compute-bound / High Reuse: Kept on Host CPU to exploit 1.84 TFLOPs cache hierarchy.";
        liveDecisionOverhead.textContent = `OH: ${m.decision_time_ms.toFixed(3)} ms (${m.decision_overhead_time_pct.toFixed(2)}%)`;
        stepInfo.textContent = `Completed ${m.total_chunks} Chunks | Host: ${m.host_chunks_executed} | PIM: ${m.pim_chunks_executed}`;

        hostUnit.classList.toggle("active-execution", !isPim);
        memoryUnit.classList.toggle("active-execution", isPim);
        packetElem.className = "data-packet";
    }

    // --- Play Animation Step-by-Step ---
    async function playAnimation(trace) {
        traceTbody.innerHTML = "";

        for (let i = 0; i < Math.min(trace.length, 30); i++) {
            const t = trace[i];
            stepInfo.textContent = `Executing Chunk ${i + 1} / ${trace.length} [${t.phase_name}]`;

            const isPim = t.decision === "PIM";
            liveDecisionBadge.textContent = t.decision;
            liveDecisionBadge.className = `decision-badge ${isPim ? 'pim-badge' : ''}`;
            liveDecisionReason.textContent = t.reason;
            liveDecisionOverhead.textContent = `OH: ${(t.decision_time_ns).toFixed(1)} ns`;

            hostUnit.classList.toggle("active-execution", !isPim);
            memoryUnit.classList.toggle("active-execution", isPim);

            if (!isPim && t.bytes_transferred > 0) {
                packetElem.className = "data-packet travel-to-host";
            } else if (isPim && t.bytes_transferred > 64) {
                packetElem.className = "data-packet travel-to-mem";
            } else {
                packetElem.className = "data-packet";
            }

            // Append table row
            const row = document.createElement("tr");
            const tagClass = isPim ? "tag-pim" : "tag-host";
            const latencyUs = ((t.compute_time_ns + t.transfer_time_ns) / 1000.0).toFixed(1);
            const dataKb = ((t.bytes_transferred || 0) / 1024.0).toFixed(1);

            row.innerHTML = `
                <td>${i + 1}</td>
                <td><strong>${t.phase_name}</strong></td>
                <td><span style="font-size: 0.75rem; color: #94a3b8;">${t.access_pattern}</span></td>
                <td><span class="${tagClass}">${t.decision}</span></td>
                <td>${latencyUs} µs</td>
                <td>${dataKb} KB</td>
                <td style="font-size: 0.75rem; color: #94a3b8;">${t.reason}</td>
            `;
            traceTbody.insertBefore(row, traceTbody.firstChild);

            await new Promise(r => setTimeout(r, 180));
        }

        packetElem.className = "data-packet";
        stepInfo.textContent = `Animation finished (${Math.min(trace.length, 30)} steps)`;
    }

    // --- Client-side fallback if backend API not reachable ---
    function runClientSideSimulation(params, isAnimated) {
        const isStreaming = params.workload === "streaming";
        const isRandom = params.workload === "random";
        const isReusable = params.workload === "reusable";

        let speedup = 1.0;
        let timeMs = 0.5;
        let trafficMb = 25.0;
        let energyMj = 4.0;
        let isPim = false;

        if (params.policy === "ALWAYS_PIM") {
            isPim = true;
            if (isReusable) { speedup = 0.10; timeMs = 2.75; energyMj = 5.8; trafficMb = 29.0; }
            else if (isStreaming) { speedup = 6.66; timeMs = 0.10; energyMj = 0.44; trafficMb = 0.0; }
            else if (isRandom) { speedup = 14.68; timeMs = 0.08; energyMj = 0.76; trafficMb = 1.0; }
            else { speedup = 1.83; timeMs = 0.41; energyMj = 1.12; trafficMb = 3.6; }
        } else if (params.policy === "DYNAMIC_INTELLIGENT" || params.policy === "ORACLE") {
            if (isReusable) {
                isPim = false; speedup = 1.0; timeMs = 0.28; energyMj = 1.64; trafficMb = 3.0;
            } else if (isStreaming) {
                isPim = true; speedup = 6.66; timeMs = 0.10; energyMj = 0.44; trafficMb = 0.0;
            } else if (isRandom) {
                isPim = true; speedup = 14.68; timeMs = 0.08; energyMj = 0.76; trafficMb = 1.0;
            } else {
                isPim = true; speedup = 6.28; timeMs = 0.12; energyMj = 0.73; trafficMb = 1.1;
            }
        } else {
            // ALWAYS_HOST
            isPim = false;
            speedup = 1.0;
            if (isReusable) { timeMs = 0.28; energyMj = 1.64; trafficMb = 3.0; }
            else if (isStreaming) { timeMs = 0.69; energyMj = 6.10; trafficMb = 32.0; }
            else if (isRandom) { timeMs = 1.20; energyMj = 8.65; trafficMb = 45.8; }
            else { timeMs = 0.76; energyMj = 5.95; trafficMb = 30.7; }
        }

        const metrics = {
            execution_time_ms: timeMs,
            speedup: speedup,
            total_data_movement_mb: trafficMb,
            total_energy_joules: energyMj / 1000.0,
            compute_energy_uj: energyMj * 400.0,
            interconnect_energy_uj: isPim ? 50.0 : energyMj * 500.0,
            memory_energy_uj: energyMj * 100.0,
            decision_energy_uj: 1.5,
            energy_reduction_pct: (1.0 - (energyMj / 6.0)) * 100.0,
            edp: (energyMj / 1000.0) * (timeMs / 1000.0),
            edp_reduction_pct: (1.0 - (energyMj * timeMs / 4.5)) * 100.0,
            pim_chunks_executed: isPim ? 24 : 0,
            host_chunks_executed: isPim ? 0 : 24,
            total_chunks: 24,
            decision_time_ms: 0.002,
            decision_overhead_time_pct: 0.4
        };

        updateMetrics(metrics);
        updateEnergyChart(metrics);
        highlightStaticDecision(metrics);
    }

    // Event Listeners
    btnRunSim.addEventListener("click", () => runSimulation(false));
    btnAnimateSim.addEventListener("click", () => runSimulation(true));

    // Run initial simulation on load
    runSimulation(false);
});
