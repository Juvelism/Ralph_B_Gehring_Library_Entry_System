const socket = io();
const disp = document.getElementById('display');

function showWaiting() {
  disp.innerHTML = `
    <h1>Fr. Ralph B. Gehring Library</h1>
    <h2 class="waiting blink">💳 Please Tap Your LST ID Card...</h2>
    <h3>Library Entry System</h3>
  `;
}

socket.on('new_attendance', (data) => {
  if (data.status === 'success') {
    disp.innerHTML = `
      <h1>Fr. Ralph B. Gehring Library</h1>
      <h2>🎉 Welcome</h2>
      <h2 class="waiting">${data.fullname}</h2>
      <h2 class="waiting">${data.idnumber}</h2>
      <h3 class="success">Entry Recorded Successfully ✅</h3>
    `;
    setTimeout(showWaiting, 4000);
  } else if (data.status === 'error') {
    disp.innerHTML = `
      <h1>❌ Fr. Ralph B. Gehring Library</h1>
      <h2 style="color:#ff4444;">Card Not Registered!</h2>
      <h3>Please go to the I.T. Office for registration.</h3>
    `;
    setTimeout(showWaiting, 4000);
  }
});

document.addEventListener('DOMContentLoaded', showWaiting);
