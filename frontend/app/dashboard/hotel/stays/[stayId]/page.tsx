import { StayDetail } from "@/components/dashboard/hotel/stay-detail";
export default async function StayPage({params}:{params:Promise<{stayId:string}>}){const {stayId}=await params;return <StayDetail stayId={stayId}/>;}
