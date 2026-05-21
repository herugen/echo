use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    collections::HashMap,
    env,
    ffi::{OsStr, OsString},
    io::{BufRead, BufReader},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::{Arc, Mutex},
    thread,
};
use tauri::{
    menu::{MenuBuilder, SubmenuBuilder},
    AppHandle, Emitter, Manager,
};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct StageSummary {
    name: String,
    status: String,
    detail: Option<String>,
    artifacts: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct AppSettings {
    output_dir: String,
    translator_backend: String,
    deepseek_base_url: String,
    deepseek_api_key: String,
}

struct AppState {
    running_tasks: Arc<Mutex<HashMap<String, u32>>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct TaskSummary {
    id: String,
    title: String,
    status: String,
    stage_label: String,
    detail: String,
    output_dir: String,
    asset_dir: String,
    progress: f64,
    stages: Vec<StageSummary>,
}

fn repo_root() -> Result<PathBuf, String> {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .and_then(Path::parent)
        .map(Path::to_path_buf)
        .ok_or_else(|| "Could not resolve repository root".to_string())
}

struct EnginePaths {
    work_dir: PathBuf,
    src_dir: PathBuf,
    python: PathBuf,
    path_env: OsString,
}

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

#[cfg(windows)]
fn hidden_command(program: impl AsRef<OsStr>) -> Command {
    let mut command = Command::new(program);
    use std::os::windows::process::CommandExt;
    command.creation_flags(CREATE_NO_WINDOW);
    command
}

#[cfg(not(windows))]
fn hidden_command(program: impl AsRef<OsStr>) -> Command {
    Command::new(program)
}

fn app_data_dir() -> Result<PathBuf, String> {
    dirs::data_dir()
        .or_else(dirs::data_local_dir)
        .map(|path| path.join("Echo"))
        .ok_or_else(|| "Could not resolve app data directory".to_string())
}

fn settings_path() -> Result<PathBuf, String> {
    Ok(app_data_dir()?.join("settings.json"))
}

fn task_db_path() -> Result<PathBuf, String> {
    Ok(app_data_dir()?.join("tasks.sqlite3"))
}

fn task_workspace_root() -> Result<PathBuf, String> {
    let path = app_data_dir()?.join("tasks");
    std::fs::create_dir_all(&path).map_err(|error| {
        format!(
            "Failed to create task workspace {}: {error}",
            path.display()
        )
    })?;
    Ok(path)
}

fn default_output_root() -> Result<PathBuf, String> {
    dirs::video_dir()
        .or_else(dirs::document_dir)
        .map(|path| path.join("Echo"))
        .ok_or_else(|| "Could not resolve a default output directory".to_string())
}

fn load_settings() -> Result<AppSettings, String> {
    let path = settings_path()?;
    if path.exists() {
        let bytes =
            std::fs::read(&path).map_err(|error| format!("Failed to read settings: {error}"))?;
        let mut settings: AppSettings = serde_json::from_slice(&bytes)
            .map_err(|error| format!("Invalid settings at {}: {error}", path.display()))?;
        if settings.output_dir.trim().is_empty() {
            settings.output_dir = default_output_root()?.display().to_string();
        }
        settings.translator_backend = "deepseek".to_string();
        if settings.deepseek_base_url.trim().is_empty() {
            settings.deepseek_base_url = "https://api.deepseek.com/v1".to_string();
        }
        Ok(settings)
    } else {
        Ok(AppSettings {
            output_dir: default_output_root()?.display().to_string(),
            translator_backend: "deepseek".to_string(),
            deepseek_base_url: "https://api.deepseek.com/v1".to_string(),
            deepseek_api_key: "".to_string(),
        })
    }
}

fn resolve_python_runtime(engine_dir: &Path) -> (PathBuf, PathBuf) {
    let candidates = if cfg!(windows) {
        vec![
            engine_dir.join("python/python.exe"),
            engine_dir.join("python/install/python.exe"),
            engine_dir.join(".venv/Scripts/python.exe"),
        ]
    } else {
        vec![
            engine_dir.join("python/install/bin/python3"),
            engine_dir.join("python/install/bin/python"),
            engine_dir.join("python/bin/python3"),
            engine_dir.join("python/bin/python"),
            engine_dir.join(".venv/bin/python"),
        ]
    };

    for candidate in candidates {
        if candidate.exists() {
            let bin_dir = candidate
                .parent()
                .map(Path::to_path_buf)
                .unwrap_or_else(|| engine_dir.to_path_buf());
            return (candidate, bin_dir);
        }
    }

    let fallback = if cfg!(windows) {
        PathBuf::from("python")
    } else {
        PathBuf::from("python3")
    };
    (fallback, engine_dir.join("bin"))
}

fn engine_paths(app: &AppHandle) -> Result<EnginePaths, String> {
    let dev_work_dir = repo_root()?;
    let dev_engine_dir = dev_work_dir.join("packages/engine");
    let bundled_engine_dir = app
        .path()
        .resource_dir()
        .map_err(|error| format!("Could not resolve resource directory: {error}"))?
        .join("engine");

    let bundled_has_runtime = bundled_engine_dir.join("python").exists()
        || bundled_engine_dir.join("python/install").exists()
        || bundled_engine_dir.join("src/echo_engine").exists();
    let engine_dir = if cfg!(debug_assertions) {
        dev_engine_dir
    } else if bundled_has_runtime {
        bundled_engine_dir
    } else {
        dev_engine_dir
    };
    let src_dir = engine_dir.join("src");
    let requires_source_tree = cfg!(debug_assertions) || !engine_dir.join("python").exists();
    if requires_source_tree && !src_dir.join("echo_engine").exists() {
        return Err(format!("Engine source not found: {}", src_dir.display()));
    }

    let (python, python_bin_dir) = resolve_python_runtime(&engine_dir);

    let mut path_entries = vec![engine_dir.join("bin"), python_bin_dir];
    if let Some(existing) = env::var_os("PATH") {
        path_entries.extend(env::split_paths(&existing));
    }
    let path_env =
        env::join_paths(path_entries).map_err(|error| format!("Failed to build PATH: {error}"))?;

    let work_dir = app_data_dir()?.join("runtime");
    std::fs::create_dir_all(&work_dir).map_err(|error| {
        format!(
            "Failed to create runtime directory {}: {error}",
            work_dir.display()
        )
    })?;

    Ok(EnginePaths {
        work_dir,
        src_dir,
        python,
        path_env,
    })
}

fn engine_pythonpath(paths: &EnginePaths) -> Result<String, String> {
    let mut entries = Vec::new();
    if paths.src_dir.join("echo_engine").exists() {
        entries.push(paths.src_dir.clone());
    }
    if let Some(existing) = env::var_os("PYTHONPATH") {
        entries.extend(env::split_paths(&existing));
    }
    env::join_paths(entries)
        .map_err(|error| format!("Failed to build PYTHONPATH: {error}"))
        .map(|value| value.to_string_lossy().to_string())
}

#[tauri::command]
fn get_settings() -> Result<AppSettings, String> {
    load_settings()
}

#[tauri::command]
fn set_output_dir(output_dir: String) -> Result<AppSettings, String> {
    let mut settings = load_settings()?;
    let output_path = PathBuf::from(output_dir);
    std::fs::create_dir_all(&output_path).map_err(|error| {
        format!(
            "Failed to create output directory {}: {error}",
            output_path.display()
        )
    })?;
    settings.output_dir = output_path.display().to_string();
    let path = settings_path()?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|error| format!("Failed to create settings dir: {error}"))?;
    }
    let bytes = serde_json::to_vec_pretty(&settings)
        .map_err(|error| format!("Failed to encode settings: {error}"))?;
    std::fs::write(path, bytes).map_err(|error| format!("Failed to write settings: {error}"))?;
    Ok(settings)
}

#[tauri::command]
fn set_translation_settings(
    deepseek_base_url: String,
    deepseek_api_key: String,
) -> Result<AppSettings, String> {
    let mut settings = load_settings()?;
    settings.translator_backend = "deepseek".to_string();
    settings.deepseek_base_url = deepseek_base_url;
    settings.deepseek_api_key = deepseek_api_key;
    let path = settings_path()?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|error| format!("Failed to create settings dir: {error}"))?;
    }
    let bytes = serde_json::to_vec_pretty(&settings)
        .map_err(|error| format!("Failed to encode settings: {error}"))?;
    std::fs::write(path, bytes).map_err(|error| format!("Failed to write settings: {error}"))?;
    Ok(settings)
}
#[tauri::command]
fn create_local_video_task(app: AppHandle, source_path: String) -> Result<TaskSummary, String> {
    let paths = engine_paths(&app)?;
    let settings = load_settings()?;
    let output_root = PathBuf::from(settings.output_dir.clone());
    std::fs::create_dir_all(&output_root).map_err(|error| {
        format!(
            "Failed to create output directory {}: {error}",
            output_root.display()
        )
    })?;
    let db_path = task_db_path()?;
    let output = hidden_command(&paths.python)
        .arg("-m")
        .arg("echo_engine.create_task_runner")
        .arg(&source_path)
        .arg("--output-root")
        .arg(&output_root)
        .arg("--workspace-root")
        .arg(task_workspace_root()?)
        .arg("--translator-base-url")
        .arg(&settings.deepseek_base_url)
        .arg("--db-path")
        .arg(&db_path)
        .env("PYTHONPATH", engine_pythonpath(&paths)?)
        .env("PATH", &paths.path_env)
        .env("DEEPSEEK_API_KEY", &settings.deepseek_api_key)
        .current_dir(&paths.work_dir)
        .output()
        .map_err(|error| format!("Failed to start engine: {error}"))?;

    if !output.status.success() {
        return Err(engine_failure_message(
            "Failed to create local video task",
            &output,
        ));
    }

    let payload: Value = serde_json::from_slice(&output.stdout)
        .map_err(|error| format!("Invalid engine response: {error}"))?;

    Ok(task_summary_from_payload(payload))
}

#[tauri::command]
fn create_url_video_task(app: AppHandle, url: String) -> Result<TaskSummary, String> {
    let paths = engine_paths(&app)?;
    let settings = load_settings()?;
    let output_root = PathBuf::from(settings.output_dir.clone());
    std::fs::create_dir_all(&output_root).map_err(|error| {
        format!(
            "Failed to create output directory {}: {error}",
            output_root.display()
        )
    })?;
    let db_path = task_db_path()?;
    let output = hidden_command(&paths.python)
        .arg("-m")
        .arg("echo_engine.create_url_task_runner")
        .arg(&url)
        .arg("--output-root")
        .arg(&output_root)
        .arg("--workspace-root")
        .arg(task_workspace_root()?)
        .arg("--translator-base-url")
        .arg(&settings.deepseek_base_url)
        .arg("--db-path")
        .arg(&db_path)
        .env("PYTHONPATH", engine_pythonpath(&paths)?)
        .env("PATH", &paths.path_env)
        .env("DEEPSEEK_API_KEY", &settings.deepseek_api_key)
        .current_dir(&paths.work_dir)
        .output()
        .map_err(|error| format!("Failed to start engine: {error}"))?;

    if !output.status.success() {
        return Err(engine_failure_message(
            "Failed to create URL video task",
            &output,
        ));
    }

    let payload: Value = serde_json::from_slice(&output.stdout)
        .map_err(|error| format!("Invalid engine response: {error}"))?;

    Ok(task_summary_from_payload(payload))
}

#[tauri::command]
fn start_task(
    app: AppHandle,
    state: tauri::State<AppState>,
    task_id: String,
) -> Result<(), String> {
    let paths = engine_paths(&app)?;
    let db_path = task_db_path()?;
    let task_id_for_thread = task_id.clone();
    let app_for_thread = app.clone();
    let running_tasks = state.running_tasks.clone();
    thread::spawn(move || {
        let mut child = match hidden_command(&paths.python)
            .arg("-m")
            .arg("echo_engine.run_task_runner")
            .arg(&task_id)
            .arg("--db-path")
            .arg(&db_path)
            .env(
                "PYTHONPATH",
                match engine_pythonpath(&paths) {
                    Ok(value) => value,
                    Err(error) => {
                        let _ = app.emit("task-error", error);
                        return;
                    }
                },
            )
            .env("PATH", &paths.path_env)
            .env(
                "DEEPSEEK_API_KEY",
                load_settings()
                    .map(|settings| settings.deepseek_api_key)
                    .unwrap_or_default(),
            )
            .current_dir(&paths.work_dir)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
        {
            Ok(child) => child,
            Err(error) => {
                let _ = app.emit("task-error", format!("Failed to start engine: {error}"));
                return;
            }
        };
        let child_pid = child.id();
        if let Ok(mut running) = running_tasks.lock() {
            running.insert(task_id_for_thread.clone(), child_pid);
        }
        if let Some(stdout) = child.stdout.take() {
            for line in BufReader::new(stdout).lines().map_while(Result::ok) {
                if let Ok(payload) = serde_json::from_str::<Value>(&line) {
                    let event_name = payload["type"].as_str().unwrap_or("task_updated");
                    if let Some(task) = payload.get("task") {
                        let _ = app.emit(event_name, task_summary_from_payload(task.clone()));
                    }
                }
            }
        }
        if let Ok(status) = child.wait() {
            let was_still_running = running_tasks
                .lock()
                .map(|mut running| running.remove(&task_id_for_thread).is_some())
                .unwrap_or(false);
            if !status.success() && was_still_running {
                let _ = app_for_thread
                    .emit("task-error", format!("Engine exited with status {status}"));
            }
        }
    });
    Ok(())
}

#[tauri::command]
fn retry_task(app: AppHandle, task_id: String) -> Result<(), String> {
    let paths = engine_paths(&app)?;
    let db_path = task_db_path()?;
    thread::spawn(move || {
        let mut child = match hidden_command(&paths.python)
            .arg("-m")
            .arg("echo_engine.retry_task_runner")
            .arg(&task_id)
            .arg("--db-path")
            .arg(&db_path)
            .env(
                "PYTHONPATH",
                match engine_pythonpath(&paths) {
                    Ok(value) => value,
                    Err(error) => {
                        let _ = app.emit("task-error", error);
                        return;
                    }
                },
            )
            .env("PATH", &paths.path_env)
            .env(
                "DEEPSEEK_API_KEY",
                load_settings()
                    .map(|settings| settings.deepseek_api_key)
                    .unwrap_or_default(),
            )
            .current_dir(&paths.work_dir)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
        {
            Ok(child) => child,
            Err(error) => {
                let _ = app.emit("task-error", format!("Failed to start engine: {error}"));
                return;
            }
        };
        if let Some(stdout) = child.stdout.take() {
            for line in BufReader::new(stdout).lines().map_while(Result::ok) {
                if let Ok(payload) = serde_json::from_str::<Value>(&line) {
                    let event_name = payload["type"].as_str().unwrap_or("task_updated");
                    if let Some(task) = payload.get("task") {
                        let _ = app.emit(event_name, task_summary_from_payload(task.clone()));
                    }
                }
            }
        }
        if let Ok(status) = child.wait() {
            if !status.success() {
                let _ = app.emit("task-error", format!("Engine exited with status {status}"));
            }
        }
    });
    Ok(())
}

#[tauri::command]
fn pause_task(
    app: AppHandle,
    state: tauri::State<AppState>,
    task_id: String,
) -> Result<TaskSummary, String> {
    let pid = state
        .running_tasks
        .lock()
        .map_err(|_| "Failed to lock running task state".to_string())?
        .remove(&task_id);
    if let Some(pid) = pid {
        kill_process(pid)?;
    }

    let paths = engine_paths(&app)?;
    let db_path = task_db_path()?;
    let output = hidden_command(&paths.python)
        .arg("-m")
        .arg("echo_engine.pause_task_runner")
        .arg(&task_id)
        .arg("--db-path")
        .arg(&db_path)
        .env("PYTHONPATH", engine_pythonpath(&paths)?)
        .env("PATH", &paths.path_env)
        .current_dir(&paths.work_dir)
        .output()
        .map_err(|error| format!("Failed to start engine: {error}"))?;
    if !output.status.success() {
        return Err(engine_failure_message("Failed to pause task", &output));
    }
    let payload: Value = serde_json::from_slice(&output.stdout)
        .map_err(|error| format!("Invalid engine response: {error}"))?;
    Ok(task_summary_from_payload(payload))
}

#[tauri::command]
fn delete_task(
    app: AppHandle,
    state: tauri::State<AppState>,
    task_id: String,
) -> Result<(), String> {
    if state
        .running_tasks
        .lock()
        .map_err(|_| "Failed to lock running task state".to_string())?
        .contains_key(&task_id)
    {
        return Err("Pause the running task before deleting it".to_string());
    }
    let paths = engine_paths(&app)?;
    let db_path = task_db_path()?;
    let output = hidden_command(&paths.python)
        .arg("-m")
        .arg("echo_engine.delete_task_runner")
        .arg(&task_id)
        .arg("--db-path")
        .arg(&db_path)
        .env("PYTHONPATH", engine_pythonpath(&paths)?)
        .env("PATH", &paths.path_env)
        .current_dir(&paths.work_dir)
        .output()
        .map_err(|error| format!("Failed to start engine: {error}"))?;
    if !output.status.success() {
        return Err(engine_failure_message("Failed to delete task", &output));
    }
    Ok(())
}

fn kill_process(pid: u32) -> Result<(), String> {
    #[cfg(windows)]
    let status = hidden_command("taskkill")
        .args(["/PID", &pid.to_string(), "/T", "/F"])
        .status();
    #[cfg(not(windows))]
    let status = Command::new("kill")
        .args(["-TERM", &pid.to_string()])
        .status();

    let status = status.map_err(|error| format!("Failed to stop task process {pid}: {error}"))?;
    if status.success() {
        Ok(())
    } else {
        Err(format!("Failed to stop task process {pid}: {status}"))
    }
}

#[tauri::command]
fn open_path(target_path: String) -> Result<(), String> {
    let path = PathBuf::from(target_path);
    if !path.exists() {
        return Err(format!("Path does not exist: {}", path.display()));
    }

    #[cfg(target_os = "macos")]
    {
        let status = if path.is_file() {
            Command::new("open").arg("-R").arg(&path).status()
        } else {
            Command::new("open").arg(&path).status()
        }
        .map_err(|error| format!("Failed to open Finder: {error}"))?;
        if status.success() {
            return Ok(());
        }
        return Err(format!("Finder exited with status {status}"));
    }

    #[cfg(target_os = "windows")]
    {
        let status = if path.is_file() {
            hidden_command("explorer")
                .arg(format!("/select,{}", path.display()))
                .status()
        } else {
            hidden_command("explorer").arg(&path).status()
        }
        .map_err(|error| format!("Failed to open Explorer: {error}"))?;
        if status.success() {
            return Ok(());
        }
        return Err(format!("Explorer exited with status {status}"));
    }

    #[cfg(target_os = "linux")]
    {
        let target = if path.is_file() {
            path.parent().unwrap_or(&path)
        } else {
            path.as_path()
        };
        let status = Command::new("xdg-open")
            .arg(target)
            .status()
            .map_err(|error| format!("Failed to open file manager: {error}"))?;
        if status.success() {
            return Ok(());
        }
        return Err(format!("File manager exited with status {status}"));
    }

    #[allow(unreachable_code)]
    Err("Opening paths is not supported on this platform".to_string())
}

#[tauri::command]
fn read_text_file(path: String) -> Result<String, String> {
    let path = PathBuf::from(path);
    if !path.exists() {
        return Err(format!("Path does not exist: {}", path.display()));
    }

    let extension = path
        .extension()
        .and_then(OsStr::to_str)
        .unwrap_or_default()
        .to_ascii_lowercase();
    if !matches!(extension.as_str(), "srt" | "vtt" | "txt") {
        return Err(format!("Unsupported text file type: {}", path.display()));
    }

    let metadata = std::fs::metadata(&path)
        .map_err(|error| format!("Failed to inspect {}: {error}", path.display()))?;
    if metadata.len() > 25 * 1024 * 1024 {
        return Err(format!("Text file is too large: {}", path.display()));
    }

    std::fs::read_to_string(&path)
        .map_err(|error| format!("Failed to read {}: {error}", path.display()))
}

#[tauri::command]
fn list_tasks(app: AppHandle) -> Result<Vec<TaskSummary>, String> {
    let paths = engine_paths(&app)?;
    let db_path = task_db_path()?;
    let output = hidden_command(&paths.python)
        .arg("-m")
        .arg("echo_engine.history_runner")
        .arg("--db-path")
        .arg(&db_path)
        .env("PYTHONPATH", engine_pythonpath(&paths)?)
        .env("PATH", &paths.path_env)
        .current_dir(&paths.work_dir)
        .output()
        .map_err(|error| format!("Failed to start engine: {error}"))?;
    if !output.status.success() {
        return Err(engine_failure_message(
            "Failed to load task history",
            &output,
        ));
    }
    let payload: Vec<Value> = serde_json::from_slice(&output.stdout)
        .map_err(|error| format!("Invalid engine response: {error}"))?;
    Ok(payload.into_iter().map(task_summary_from_payload).collect())
}

fn engine_failure_message(context: &str, output: &std::process::Output) -> String {
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let detail = if !stderr.is_empty() {
        stderr
    } else if !stdout.is_empty() {
        stdout
    } else {
        format!("process exited with status {}", output.status)
    };
    format!("{context}: {detail}")
}

fn task_summary_from_payload(payload: Value) -> TaskSummary {
    TaskSummary {
        id: payload["id"].as_str().unwrap_or_default().to_string(),
        title: payload["title"].as_str().unwrap_or_default().to_string(),
        status: payload["status"].as_str().unwrap_or_default().to_string(),
        stage_label: if payload["status"].as_str() == Some("succeeded") {
            "处理已完成".to_string()
        } else {
            payload["current_stage"]
                .as_str()
                .unwrap_or_default()
                .to_string()
        },
        detail: format!(
            "输出目录：{}",
            payload["config"]["output_dir"].as_str().unwrap_or_default()
        ),
        output_dir: payload["config"]["output_dir"]
            .as_str()
            .unwrap_or_default()
            .to_string(),
        asset_dir: payload["asset_dir"]
            .as_str()
            .unwrap_or_default()
            .to_string(),
        progress: payload["progress"].as_f64().unwrap_or_default(),
        stages: payload["stages"]
            .as_array()
            .map(|stages| {
                stages
                    .iter()
                    .map(|stage| StageSummary {
                        name: stage["name"].as_str().unwrap_or_default().to_string(),
                        status: stage["status"].as_str().unwrap_or_default().to_string(),
                        detail: stage["detail"].as_str().map(str::to_string),
                        artifacts: stage["artifacts"]
                            .as_array()
                            .map(|artifacts| {
                                artifacts
                                    .iter()
                                    .filter_map(|artifact| artifact.as_str().map(str::to_string))
                                    .collect()
                            })
                            .unwrap_or_default(),
                    })
                    .collect()
            })
            .unwrap_or_default(),
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(AppState {
            running_tasks: Arc::new(Mutex::new(HashMap::new())),
        })
        .setup(|app| {
            let app_menu = SubmenuBuilder::new(app, "Echo")
                .about(None)
                .separator()
                .text("open_settings", "Settings…")
                .separator()
                .hide()
                .hide_others()
                .separator()
                .quit()
                .build()?;
            let file_menu = SubmenuBuilder::new(app, "File")
                .text("open_settings_file", "Settings…")
                .separator()
                .close_window()
                .build()?;
            let edit_menu = SubmenuBuilder::new(app, "Edit")
                .undo()
                .redo()
                .separator()
                .cut()
                .copy()
                .paste()
                .separator()
                .select_all()
                .build()?;
            let menu = MenuBuilder::new(app)
                .item(&app_menu)
                .item(&file_menu)
                .item(&edit_menu)
                .build()?;
            app.set_menu(menu)?;
            app.on_menu_event(|app, event| {
                let id = event.id().as_ref();
                if id == "open_settings" || id == "open_settings_file" {
                    let _ = app.emit("open_settings", ());
                }
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_settings,
            set_output_dir,
            set_translation_settings,
            create_local_video_task,
            create_url_video_task,
            start_task,
            retry_task,
            pause_task,
            delete_task,
            open_path,
            read_text_file,
            list_tasks
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
