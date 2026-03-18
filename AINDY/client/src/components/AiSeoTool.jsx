import { useState } from "react";
import axios from "axios";

export default function AiSeoTool() {
    const [content, setContent] = useState("");
    const [seoData, setSeoData] = useState(null);
    const [metaDescription, setMetaDescription] = useState("");
    const [seoSuggestions, setSeoSuggestions] = useState("");
    const [loading, setLoading] = useState(false);

    const analyzeSeo = async () => {
        setLoading(true);
        try {
            const response = await axios.post("http://localhost:8000/analyze_seo/", { content });
            setSeoData(response.data);
        } catch (error) {
            console.error("SEO Analysis Error: ", error);
        }
        setLoading(false);
    };

    const generateMeta = async () => {
        setLoading(true);
        try {
            const response = await axios.post("http://localhost:8000/generate_meta/", { content });
            setMetaDescription(response.data.meta_description);
        } catch (error) {
            console.error("Meta Description Error: ", error);
        }
        setLoading(false);
    };

    const getSeoSuggestions = async () => {
        setLoading(true);
        try {
            const response = await axios.post("http://localhost:8000/suggest_improvements/", { content });
            setSeoSuggestions(response.data.seo_suggestions);
        } catch (error) {
            console.error("SEO Suggestions Error: ", error);
        }
        setLoading(false);
    };

    return (
        <div className="container mx-auto p-6 text-white bg-black min-h-screen">
            <h1 className="text-3xl font-bold mb-6 text-blue-400">AI SEO Optimization Tool</h1>
            
            {/* TEXTAREA SECTION */}
            <div className="mb-4">
                <label className="block text-sm font-medium text-gray-400 mb-2">Article Content</label>
                <textarea
                    className="w-full p-4 bg-zinc-900 border border-zinc-700 rounded-lg text-white placeholder-gray-500 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all"
                    rows="8"
                    placeholder="Paste your article or blog content here for analysis..."
                    value={content}
                    onChange={(e) => setContent(e.target.value)}
                ></textarea>
            </div>

            {/* ACTION BUTTONS */}
            <div className="flex flex-wrap gap-4 mt-4">
                <button 
                    className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-md transition-colors disabled:opacity-50" 
                    onClick={analyzeSeo}
                    disabled={loading || !content}
                >
                    Analyze SEO
                </button>
                <button 
                    className="px-6 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold rounded-md transition-colors disabled:opacity-50" 
                    onClick={generateMeta}
                    disabled={loading || !content}
                >
                    Generate Meta
                </button>
                <button 
                    className="px-6 py-2 bg-purple-600 hover:bg-purple-700 text-white font-semibold rounded-md transition-colors disabled:opacity-50" 
                    onClick={getSeoSuggestions}
                    disabled={loading || !content}
                >
                    Get Suggestions
                </button>
            </div>

            {/* LOADING INDICATOR */}
            {loading && (
                <div className="mt-6 flex items-center gap-2 text-blue-400 animate-pulse">
                    <div className="w-2 h-2 bg-blue-400 rounded-full"></div>
                    <p>A.I.N.D.Y. is analyzing your content...</p>
                </div>
            )}

            {/* RESULTS SECTIONS */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-8">
                
                {/* SEO ANALYSIS BOX */}
                {seoData && (
                    <div className="p-6 bg-zinc-900 border border-zinc-800 rounded-xl shadow-lg">
                        <h2 className="text-xl font-bold mb-4 text-blue-400 border-b border-zinc-800 pb-2">SEO Scorecard</h2>
                        <div className="space-y-2 text-gray-300">
                            <p><strong className="text-white">Word Count:</strong> {seoData.word_count}</p>
                            <p><strong className="text-white">Readability:</strong> <span className="text-emerald-400">{seoData.readability}</span></p>
                            <p><strong className="text-white">Top Keywords:</strong> {seoData.top_keywords.join(", ")}</p>
                            
                            <h3 className="mt-4 font-bold text-white">Keyword Densities:</h3>
                            <ul className="grid grid-cols-2 gap-2 mt-2">
                                {Object.entries(seoData.keyword_densities).map(([keyword, density]) => (
                                    <li key={keyword} className="bg-zinc-800 p-2 rounded text-sm border border-zinc-700">
                                        <span className="text-gray-400">{keyword}:</span> <span className="text-blue-300">{density}%</span>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    </div>
                )}

                {/* META DESCRIPTION BOX */}
                {metaDescription && (
                    <div className="p-6 bg-zinc-900 border border-zinc-800 rounded-xl shadow-lg">
                        <h2 className="text-xl font-bold mb-4 text-emerald-400 border-b border-zinc-800 pb-2">Meta Description</h2>
                        <p className="italic text-gray-300 leading-relaxed">"{metaDescription}"</p>
                        <button 
                            className="mt-4 text-xs text-zinc-500 hover:text-white underline"
                            onClick={() => navigator.clipboard.writeText(metaDescription)}
                        >
                            Copy to clipboard
                        </button>
                    </div>
                )}

                {/* SUGGESTIONS BOX */}
                {seoSuggestions && (
                    <div className="p-6 bg-zinc-900 border border-zinc-800 rounded-xl shadow-lg md:col-span-2">
                        <h2 className="text-xl font-bold mb-4 text-purple-400 border-b border-zinc-800 pb-2">Improvement Strategy</h2>
                        <p className="text-gray-300 whitespace-pre-wrap">{seoSuggestions}</p>
                    </div>
                )}
            </div>
        </div>
    );
}
