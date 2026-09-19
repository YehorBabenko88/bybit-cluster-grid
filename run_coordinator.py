import uvicorn
if __name__=="__main__":
    uvicorn.run("grid.coordinator:app",host="0.0.0.0",port=8765)
