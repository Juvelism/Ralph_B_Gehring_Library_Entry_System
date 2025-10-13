function fetchLatest() {
  fetch("/api/latest")
    .then(res => res.json())
    .then(data => {
      if (data.status === "success") {
        document.getElementById("status").innerText = "✅ Attendance Recorded!";
        document.getElementById("student-name").innerText = data.firstname || "Unknown";
        document.getElementById("student-id").innerText = data.idnumber || "No ID";
      } else if (data.status === "waiting") {
        document.getElementById("status").innerText = "Waiting for card...";
        document.getElementById("student-name").innerText = "";
        document.getElementById("student-id").innerText = "";
      } else {
        document.getElementById("status").innerText = "❌ Unknown card tapped!";
      }
    })
    .catch(err => console.error("Error:", err));
}

fetchLatest();
setInterval(fetchLatest, 2000);
