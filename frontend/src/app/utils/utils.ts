export function accessibleRouteChangeHandler() {
  return window.setTimeout(() => {
    const mainContainer = document.getElementById('primary-app-container');
    if (mainContainer) {
      mainContainer.focus();
    }
  }, 50);
}

export function getErrorMessage(error){
  let message = "";
  if (error.response) {
    message = `Recieved HTTP status ${error.response.status} from server. Response: ${error.response.data.message}`;
  } else if (error.request) {
    message = "Unable to get response from server";
  } else {
    message = "Error initializing request";
  }
  return message
}
