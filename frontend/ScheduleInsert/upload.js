import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

// === Supabase project connection ===
const supabaseUrl = "https://xnrkwswqnkjptnuuveer.supabase.co";
const supabaseAnonKey =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inhucmt3c3dxbmtqcHRudXV2ZWVyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTk2MjA4MjYsImV4cCI6MjA3NTE5NjgyNn0.HNlHsELBUter8XfY3qSWMzyQun82hcHKGIWV_wEHDrA";

const supabase = createClient(supabaseUrl, supabaseAnonKey);

// === Elements ===
const dropbox = document.getElementById("dropbox");
const fileInput = document.getElementById("fileInput");
const uploadBtn = document.getElementById("uploadBtn");
const msg = document.getElementById("msg");
const groupCode = document.getElementById("groupCode");
const userName = document.getElementById("userName");
const preview = document.getElementById("preview");

let selectedFile = null;

// === Handle file selection ===
dropbox.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", (e) => handleFiles(e.target.files));

function handleFiles(files) {
  if (!files || !files[0]) return;
  const f = files[0];
  selectedFile = f;

  const reader = new FileReader();
  reader.onload = (e) => {
    dropbox.style.backgroundImage = `url(${e.target.result})`;
    dropbox.style.backgroundSize = "cover";
    dropbox.style.backgroundPosition = "center";
    preview.src = e.target.result;
    preview.style.display = "block";
    uploadBtn.disabled = false;
  };
  reader.readAsDataURL(f);
}

// === Upload ===
uploadBtn.addEventListener("click", async () => {
  if (!selectedFile || !userName.value.trim()) {
    msg.textContent = "⚠️ Please provide a name and choose an image.";
    return;
  }

  msg.textContent = "⏳ Uploading schedule...";

  const reader = new FileReader();
  reader.onload = async (e) => {
    const base64Data = e.target.result.split(",")[1]; // strip prefix

    try {
      const { data, error } = await supabase
        .from("schedules")
        .insert([
          {
            group_id: groupCode.value || null,
            user_name: userName.value,
            classes: { image_base64: base64Data },
          },
        ])
        .select();

      if (error) throw error;

      msg.textContent = "✅ Schedule successfully saved!";
      console.log("Inserted:", data);
    } catch (err) {
      msg.textContent = "❌ Upload failed: " + err.message;
      console.error(err);
    }
  };
  reader.readAsDataURL(selectedFile);
});

