const formatMoney = (value) => value == null ? "—" : `$${Number(value).toFixed(2)}`;
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
}[character]));

async function getJson(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return response.json();
}

function renderCards(data) {
  const cards = [
    ["Current tracked cost", formatMoney(data.estimated_cost)],
    ["Month to date", formatMoney(data.month_to_date_cost)],
    ["30-day forecast", formatMoney(data.predicted_monthly_cost)],
    ["Likely idle instances", data.idle_instances_count ?? "—"],
  ];
  document.querySelector("#cards").innerHTML = cards.map(([label, value]) =>
    `<article class="card"><p class="muted">${label}</p><p class="card-value">${value}</p></article>`
  ).join("");
  const badge = document.querySelector("#connectionBadge");
  badge.textContent = data.aws_connected ? "AWS connected" : `${data.mode} mode`;
}

function renderInstances(data) {
  if (!data.instances.length) {
    document.querySelector("#instances").textContent = "No instances found. Try a refresh.";
    return;
  }
  document.querySelector("#instances").innerHTML = `
    <table><thead><tr><th>Name</th><th>Type</th><th>CPU</th><th>Status</th></tr></thead>
    <tbody>${data.instances.map((item) => `
      <tr><td>${escapeHtml(item.name || "Unnamed")}</td><td>${escapeHtml(item.type)}</td>
      <td>${item.cpu == null ? "—" : `${Number(item.cpu).toFixed(1)}%`}</td>
      <td>${item.cpu != null && item.cpu <= 10 ? "Review" : "Monitoring"}</td></tr>
    `).join("")}</tbody></table>`;
}

async function refresh() {
  try {
    const [dashboard, instances] = await Promise.all([
      getJson("/api/dashboard"),
      getJson("/api/instances"),
    ]);
    renderCards(dashboard);
    renderInstances(instances);
  } catch (error) {
    document.querySelector("#connectionBadge").textContent = "Backend unavailable";
    document.querySelector("#instances").textContent = error.message;
  }
}

document.querySelector("#refreshButton").addEventListener("click", refresh);
document.querySelector("#assistantForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = document.querySelector("#question");
  const answer = document.querySelector("#answer");
  answer.textContent = "Thinking...";
  try {
    const result = await getJson("/api/assistant", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: input.value }),
    });
    answer.textContent = result.answer;
  } catch (error) {
    answer.textContent = error.message;
  }
});

document.querySelector("#awsForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const result = document.querySelector("#awsResult");
  result.textContent = "Validating role...";
  try {
    const response = await getJson("/api/aws/validate-role", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        role_arn: document.querySelector("#roleArn").value,
        external_id: document.querySelector("#externalId").value,
      }),
    });
    result.textContent = `Connected to AWS account ${response.account_id || "successfully"}.`;
  } catch (error) {
    result.textContent = `Connection failed: ${error.message}`;
  }
});

document.querySelector("#alertForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const result = document.querySelector("#alertResult");
  result.textContent = "Sending test alert...";
  try {
    const response = await getJson("/api/alerts/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: document.querySelector("#provider").value,
        webhook_url: document.querySelector("#webhookUrl").value,
        message: "Cloud Cost Copilot test alert",
      }),
    });
    result.textContent = `${response.provider} test alert sent.`;
  } catch (error) {
    result.textContent = `Alert failed: ${error.message}`;
  }
});

refresh();
